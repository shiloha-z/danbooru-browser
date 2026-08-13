"""Session state serialization: the workflow-JSON truth."""

from __future__ import annotations

import pytest

from core.errors import StateError
from core.model import SearchConditions
from core.session import Page, SessionState, session_from_json, session_to_json

from fakes import make_post


def make_state() -> SessionState:
    posts = [make_post(1), make_post(2, tags=("2girls", "hug"))]
    return SessionState(
        conditions=SearchConditions(site="danbooru", tags=("1girl",), per_page=40),
        pages=[Page(number=1, posts=posts)],
        cursor=0,
        selection=2,
    )


class TestRoundtrip:
    def test_state_roundtrip(self):
        state = make_state()
        restored = session_from_json(session_to_json(state))
        assert restored.conditions == state.conditions
        assert [p.id for p in restored.pages[0].posts] == [1, 2]
        assert restored.selection == 2
        assert restored.cursor == 0
        assert restored.pages[0].posts[0].raw == state.pages[0].posts[0].raw

    def test_empty_state_roundtrip(self):
        restored = session_from_json(session_to_json(SessionState()))
        assert restored.conditions is None
        assert restored.pages == []
        assert restored.selection is None

    def test_empty_string_is_empty_state(self):
        state = session_from_json("")
        assert state.conditions is None

    def test_malformed_json_raises(self):
        with pytest.raises(StateError):
            session_from_json("{not json")

    def test_wrong_shape_raises(self):
        with pytest.raises(StateError):
            session_from_json('{"conditions": 42}')
        with pytest.raises(StateError):
            session_from_json('[1, 2, 3]')
