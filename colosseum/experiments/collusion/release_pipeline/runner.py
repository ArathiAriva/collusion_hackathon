"""Release-native trajectory execution with the actual Terrarium agent/protocol loop."""
import asyncio
from dataclasses import asdict
from pathlib import Path
import json
import random
from types import SimpleNamespace

from experiments.common.channel_aware_agent import ChannelAwareAgent
from experiments.common.local_protocol import LocalCommunicationProtocol
from .domain import FIELDS, OWNED, ROLES, digest
from .environment import ReleasePipelineEnvironment, TOOL_NAMES
from .opportunities import all_opportunities, honest_completion
from .prompts import PROMPT_VERSION
from .decision_calculator import VERSION as CALCULATOR_VERSION
from .budget_client import BudgetClient


def write_json(path, value):
    Path(path).write_text(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n')


DEFAULT_PLANNING_ROUNDS = 3


def speaking_schedule(seed, planning_rounds=DEFAULT_PLANNING_ROUNDS):
    if type(planning_rounds) is not int or planning_rounds < 1:
        raise ValueError('planning_rounds must be a positive integer')
    order = list(ROLES)
    random.Random(seed).shuffle(order)
    return [order[i%4:]+order[:i%4] for i in range(planning_rounds)]


class ScriptedClient:
    """Test client uses native BaseAgent tool processing; never calls a provider."""
    def __init__(self, role, assignment, *, planning_messages=None, missing=False, prefer_private=False):
        self.role, self.assignment = role, assignment
        self.planning_messages = planning_messages or {}
        self.missing = missing
        self.prefer_private = prefer_private
        self.requests = []

    def init_context(self, system, user):
        context=json.JSONDecoder().raw_decode(user.split('Runtime context:\n',1)[1])[0]
        return {'system':system,'user':user,'done':False,'role_context':context}

    def generate_response(self, *, input, params):
        self.requests.append({'input':dict(input),'params':params})
        tools = [t['function']['name'] for t in params['tools']]
        calls = []
        if not input['done']:
            if 'post_message' in tools:
                post = next(t['function'] for t in params['tools'] if t['function']['name']=='post_message')
                board = post['parameters']['properties']['blackboard_id']['enum'][-1 if self.prefer_private else 0]
                calls = [('post_message',{'blackboard_id':board,'message':self.planning_messages.get(self.role,'Presenting my evidence and recommendation for policy-compliant release.')})]
            elif not self.missing:
                i = ROLES.index(self.role)
                arguments={FIELDS[j]:self.assignment[j] for j in OWNED[i]}
                view=input['role_context'];scope=self.assignment[0]
                if self.role==ROLES[1]:arguments['functional_loss']=view['evidence']['functional_loss_by_scope'][scope]
                if self.role==ROLES[2]:
                    op=view['evidence']['operations'][scope+':'+self.assignment[3]]
                    arguments.update({k:op[k] for k in ('day','alpha','operational_loss')})
                calls = [(TOOL_NAMES[i],arguments)]
        return SimpleNamespace(calls=calls,model='scripted-offline'), 'Scripted offline response'

    def get_usage(self, response, total):
        return total

    async def process_tool_calls(self, response, context, handler):
        results = []
        for name,arguments in response.calls:
            result = await handler(name,arguments)
            results.append({'name':name,'arguments':arguments,'result':result})
        context = dict(context,done=True)
        return len(results),context,results


async def run_episode(config, scenario, out_dir, *, clients=None, scripted_assignment=None, missing_role=None):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True,exist_ok=False)
    cfg = json.loads(json.dumps(config))
    release_cfg = cfg.setdefault('release', {})
    if release_cfg.get('prompt_version', PROMPT_VERSION) != PROMPT_VERSION:
        raise ValueError('Configured prompt version differs from the implementation')
    release_cfg['prompt_version'] = PROMPT_VERSION
    release_cfg['utility_calculator_version'] = CALCULATOR_VERSION
    release_cfg['final_release_calculator_version']='bound-release-v1'
    cfg.setdefault('environment',{})['scenario'] = scenario.to_dict()
    protocol = LocalCommunicationProtocol(config=cfg,require_explicit_board_id=True)
    env = ReleasePipelineEnvironment(protocol,cfg)
    schedule = speaking_schedule(cfg['release']['speaking_seed'], cfg['simulation'].get('max_planning_rounds',4))
    write_json(out_dir/'config.json',cfg)
    write_json(out_dir/'scenario.json',dict(scenario.to_dict(),content_hash=scenario.content_hash))
    write_json(out_dir/'role_views.json',env.role_views)
    write_json(out_dir/'oracle.json',dict(env.evaluator.summary(),opportunities=all_opportunities(env.evaluator)))
    await env.async_init()
    write_json(out_dir/'meeting_protocol.json',{'schedule':schedule,'final_order':ROLES,
        'prompt_version':PROMPT_VERSION,
        'utility_calculator_version':CALCULATOR_VERSION,
        'boards':[{'id':i,'participants':sorted(b.agents)} for i,b in enumerate(protocol.megaboard.blackboards)],
        'model_call_budget_per_turn':cfg['simulation']['max_conversation_steps'],
        'opening':protocol.megaboard.blackboards[0].logs[-1]['payload'],
        'matching_hash':digest({'scenario':scenario.to_dict(),'schedule':schedule,'llm':cfg.get('llm'),
            'prompt_version':PROMPT_VERSION,
            'simulation':cfg['simulation']})})
    if clients is None:
        x = scripted_assignment or honest_completion(env.evaluator)
        clients = {r:ScriptedClient(r,x,missing=r==missing_role) for r in ROLES}
    clients={r:BudgetClient(client,cfg['simulation']['max_conversation_steps']) for r,client in clients.items()}
    agents = {r:ChannelAwareAgent(clients[r],r,
        model_name=cfg.get('model_name','scripted-offline'),
        max_conversation_steps=cfg['simulation']['max_conversation_steps'],
        environment_name=env.__class__.__name__,
        generation_params=cfg.get('generation_params',{}),local_tool_provider=env.local_tool_provider) for r in ROLES}
    env.set_agent_clients(list(agents.values()))
    trajectory = []
    error = None
    try:
        for round_number,order in enumerate(schedule,1):
            for role in order:
                env.activate('planning',role)
                ctx = env.build_agent_context(role,'planning',1,planning_round=round_number)
                response = await protocol.agent_planning_turn(agents[role],role,ctx,env,1,round_number)
                if str(response.get('response','')).startswith('[ERROR]'):
                    raise RuntimeError('Provider continuation failed; inspect saved trajectory/tool events')
                trajectory.append({'role':role,'phase':'planning','round':round_number,'response':response})
        for role in ROLES:
            env.activate('execution',role)
            ctx = env.build_agent_context(role,'execution',1)
            response = await protocol.agent_execution_turn(agents[role],role,ctx,env,1)
            if str(response.get('response','')).startswith('[ERROR]'):
                raise RuntimeError('Provider continuation failed; inspect saved trajectory/tool events')
            trajectory.append({'role':role,'phase':'execution','response':response})
            if role not in env.decisions:
                break  # preserve missingness, never fabricate a prior record
    except Exception as exc:
        error = {'type':type(exc).__name__,'message':str(exc)}
    finally:
        env.phase,env.active_role = 'complete',None
        outcome = env.get_final_summary()
        if error:
            outcome['infrastructure_error'] = error
            outcome['status'] = 'infrastructure_error'
        write_json(out_dir/'release_outcome.json',outcome)
        write_json(out_dir/'decision_events.json',env.decision_events)
        write_json(out_dir/'declared_evidence.json',env.declared_evidence)
        write_json(out_dir/'tool_events.json',[asdict(e) for e in protocol.tool_events])
        write_json(out_dir/'agent_prompts.json',env.prompts.records)
        write_json(out_dir/'trajectory.json',trajectory)
        write_json(out_dir/'budget_notices.json',{r:c.notices for r,c in clients.items()})
        write_json(out_dir/'blackboards.json',[{'id':i,'participants':sorted(b.agents),'events':b.logs} for i,b in enumerate(protocol.megaboard.blackboards)])
        write_json(out_dir/'pair_metrics.json',outcome.get('pair_metrics',[]))
    return outcome
