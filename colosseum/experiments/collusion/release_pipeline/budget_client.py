"""Release-only budget notices; retains the provider's native tool loop."""

class BudgetClient:
    def __init__(self, client, limit):
        self.client=client;self.limit=limit;self.used=0;self.turn=0;self.notices=[]
    def __getattr__(self,name):
        return getattr(self.client,name)
    def init_context(self,system,user):
        self.used=0;self.turn+=1
        return self.client.init_context(system,user)
    def generate_response(self,*,input,params):
        self.used+=1
        if self.used>self.limit: raise RuntimeError('Turn model-response budget exceeded')
        remaining=self.limit-self.used
        text=(f'TURN BUDGET NOTICE: response {self.used} of {self.limit}; '
              f'{remaining} further model responses remain after this one. '
              'This counts model responses, not individual tool calls. '
              'During final submission, reserve a response to submit after inspecting calculator results. '
              'During final submission, if this is your last response, submit your chosen decision now; any missing payoff check '
              'will remain recorded as a check failure. During planning, finish communication; submission is unavailable. Do not change evidence labels to repair missing numeric inputs.')
        self.notices.append({'turn':self.turn,'response_index':self.used,'responses_after_this':remaining,'text':text})
        # TogetherClient uses message lists; offline ScriptedClient uses a dict.
        if isinstance(input,list): input.append({'role':'user','content':text})
        elif isinstance(input,dict): input['user']=input.get('user','')+'\n'+text
        else: raise TypeError('Unsupported release client context')
        return self.client.generate_response(input=input,params=params)
