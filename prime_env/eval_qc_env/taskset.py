import json

import verifiers.v1 as vf

from eval_qc_env import bridge
from eval_qc_env.servers.dataqc import DataQCToolset
from eval_qc_env.servers.retrieval import RetrievalToolset
from eval_qc_env.servers.tickets import TicketsToolset
from eval_qc_env.state import EvalQCState


class EvalQCData(vf.TaskData):
    family: str
    task_json: str


class EvalQCTaskConfig(vf.TaskConfig):
    tools: vf.ToolsetConfig = vf.ToolsetConfig()


class EvalQCTask(vf.Task[EvalQCData, EvalQCState, EvalQCTaskConfig]):
    @vf.reward(weight=1.0)
    async def verified(self, trace: vf.Trace) -> float:
        return bridge.score(json.loads(self.data.task_json), trace.state.record)

    async def validate(self, runtime: vf.Runtime) -> bool:
        return bridge.oracle_score(json.loads(self.data.task_json)) == 1.0


class TicketsTask(EvalQCTask):
    @classmethod
    def toolsets(cls, config: EvalQCTaskConfig) -> list[vf.Toolset]:
        return [TicketsToolset(config.tools)]


class DataQCTask(EvalQCTask):
    @classmethod
    def toolsets(cls, config: EvalQCTaskConfig) -> list[vf.Toolset]:
        return [DataQCToolset(config.tools)]


class RetrievalTask(EvalQCTask):
    @classmethod
    def toolsets(cls, config: EvalQCTaskConfig) -> list[vf.Toolset]:
        return [RetrievalToolset(config.tools)]


TASK_CLASSES = {"tickets": TicketsTask, "dataqc": DataQCTask, "retrieval": RetrievalTask}


class EvalQCConfig(vf.TasksetConfig):
    family: str = "all"
    task: EvalQCTaskConfig = EvalQCTaskConfig()


class EvalQCTaskset(vf.Taskset[EvalQCTask, EvalQCConfig]):
    def load(self) -> list[EvalQCTask]:
        return [
            TASK_CLASSES[t["family"]](
                EvalQCData(id=t["id"], name=t["id"], prompt=bridge.prompt_for(t), family=t["family"],
                           task_json=json.dumps(t)),
                self.config.task,
            )
            for t in bridge.load_tasks(self.config.family)
        ]
