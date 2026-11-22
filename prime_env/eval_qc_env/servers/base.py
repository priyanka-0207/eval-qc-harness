import json

import verifiers.v1 as vf

from eval_qc_env import bridge
from eval_qc_env.state import EvalQCState


class FamilyToolset(vf.Toolset[vf.ToolsetConfig, EvalQCState]):
    async def setup_task(self, task):
        self.task = json.loads(task.task_json)
        self.env_state = bridge.new_state(self.task)

    def _call(self, tool, **args):
        result = bridge.call(self.task, self.env_state, tool, args)
        self.state.record = bridge.record(self.task, self.env_state)
        return result
