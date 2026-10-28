from streamlit.testing.v1 import AppTest
from pathlib import Path

def bylabel(elements,label):
 return next(e for e in elements if e.label==label)
def check(at,stage):
 err=[e.message for e in at.exception]
 print(stage,'errors=',err,'titles=',[x.value for x in at.title], flush=True)
 if err: raise RuntimeError(stage+': '+str(err))

at=AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'),default_timeout=60).run(); check(at,'real-data start')
bylabel(at.selectbox,'Dataset').set_value('Synthetic factory').run(); check(at,'synthetic start')
at.radio[0].set_value('Production Planning').run(); check(at,'planning')
bylabel(at.button,'Optimize production quantities').click().run(); check(at,'plan-solve')
print('success:',[x.value for x in at.success],flush=True)
bylabel(at.button,'Use planned quantities for scheduling').click().run(); check(at,'apply plan')
at.radio[0].set_value('Scheduling').run(); check(at,'scheduling')
bylabel(at.slider,'CP-SAT time limit (seconds)').set_value(4)
bylabel(at.button,'Run CP-SAT optimization').click().run(timeout=60); check(at,'solve scheduling')
print('info:',[x.value for x in at.info],flush=True)
print('warnings:',[x.value for x in at.warning],flush=True)
print('dataframes:',len(at.dataframe),flush=True)
at.radio[0].set_value('Gantt Chart').run(timeout=60); check(at,'gantt')
at.radio[0].set_value('Rescheduling').run(); check(at,'resched form')
print('resched buttons', [x.label for x in at.button],flush=True)
bylabel(at.slider,'Re-optimization limit (seconds)').set_value(4)
bylabel(at.button,'Simulate breakdown & re-optimize').click().run(timeout=60); check(at,'breakdown')
print('breakdown infos:',[x.value for x in at.info],flush=True)
bylabel(at.selectbox,'Scenario').set_value('Urgent order').run(); check(at,'urgent form')
bylabel(at.slider,'Re-optimization limit (seconds)').set_value(4)
bylabel(at.button,'Insert urgent order & re-optimize').click().run(timeout=60); check(at,'urgent solve')
print('urgent infos:',[x.value for x in at.info],flush=True)
at.radio[0].set_value('Schedule Comparison').run(); check(at,'comparison')
print('capacity buttons',[x.label for x in at.button],flush=True)
bylabel(at.slider,'What-if solve limit (seconds)').set_value(4)
bylabel(at.button,'Run capacity what-if').click().run(timeout=60); check(at,'capacity solve')
at.radio[0].set_value('Model Configuration').run(); check(at,'configuration')
print('PASS app smoke',flush=True)
