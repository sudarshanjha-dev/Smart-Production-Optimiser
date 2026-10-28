from pathlib import Path
from streamlit.testing.v1 import AppTest


def test_app_navigation_baselines_and_gantt():
    root = Path(__file__).resolve().parents[1]
    app = AppTest.from_file(str(root / 'app.py'), default_timeout=25).run()
    assert not app.exception
    next(s for s in app.selectbox if s.label == 'Dataset').set_value('Synthetic factory').run()
    assert not app.exception
    assert app.title[0].value == 'Configure the factory'
    app.radio[0].set_value('Scheduling').run()
    assert not app.exception
    next(b for b in app.button if b.label == 'Generate dispatching baselines only').click().run()
    assert not app.exception
    app.radio[0].set_value('Gantt Chart').run()
    assert not app.exception
    assert app.title[0].value == 'Inspect the production sequence'
    app.radio[0].set_value('Model Configuration').run()
    assert not app.exception
