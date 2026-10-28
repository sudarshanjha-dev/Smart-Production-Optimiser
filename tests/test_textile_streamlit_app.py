from pathlib import Path
from streamlit.testing.v1 import AppTest


def by_label(elements, label):
    return next(element for element in elements if element.label == label)


def test_default_textile_workspace_solve_and_switch():
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'), default_timeout=35).run()
    assert not app.exception
    assert app.title[0].value == 'Schedule the textile line'
    assert by_label(app.selectbox, 'Dataset').value == 'Real textile case study'
    assert any('Harden[1] TM2' in w.value for w in app.warning)
    by_label(app.number_input, 'CP-SAT time limit (seconds)').set_value(2)
    by_label(app.button, 'Run textile optimization').click().run(timeout=35)
    assert not app.exception
    result = app.session_state['textile_result']
    assert result.status in {'FEASIBLE', 'OPTIMAL', 'UNKNOWN'}
    if result.has_schedule:
        assert any('Independent validation passed' in x.value for x in app.success)
        assert len(app.dataframe) >= 4
        assert any('Download validated textile schedule CSV' == x.label for x in app.get('download_button'))
    by_label(app.selectbox, 'Order interpretation').set_value('Paper narrative: second → first').run()
    assert not app.exception
    assert any('Choose an interpretation and objective' in x.value for x in app.info)
    by_label(app.selectbox, 'Dataset').set_value('Synthetic factory').run()
    assert not app.exception and app.title[0].value == 'Configure the factory'


def test_profile_objective_controls_display():
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'), default_timeout=35).run()
    by_label(app.selectbox, 'Objective').set_value('Minimize total mode profile under a makespan cap').run()
    assert not app.exception
    assert by_label(app.number_input, 'Makespan cap (working slots)').value == 1152
    assert any('not grid cost or kWh' in c.value for c in app.caption)


def test_textile_profile_run_and_relaxed_policy():
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'), default_timeout=35).run()
    by_label(app.selectbox, 'Same-unit task policy').set_value('Allow independent tasks of a unit to overlap').run()
    by_label(app.selectbox, 'Objective').set_value('Minimize total mode profile under a makespan cap').run()
    by_label(app.number_input, 'Makespan cap (working slots)').set_value(1016)
    by_label(app.number_input, 'CP-SAT time limit (seconds)').set_value(2)
    by_label(app.button, 'Run textile optimization').click().run(timeout=35)
    assert not app.exception
    result = app.session_state['textile_result']
    assert result.status in {'FEASIBLE','OPTIMAL','UNKNOWN'}
    assert result.metadata['objective'] == 'total_mode_profile_raw'
    assert result.metadata['unit_exclusive'] is False
    if result.has_schedule:
        assert result.schedule.end_slot.max() <= 1016
        assert any('Independent validation passed' in x.value for x in app.success)
