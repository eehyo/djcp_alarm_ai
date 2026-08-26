import json

import pytest

from djcp_alarm_ai.cli.load_tag_description import _row_params


def test_row_params_maps_fields_and_serializes_related_tags():
    record = {
        "tag_id": "10011217",
        "tag_name": "BBAIT-801",
        "description": "연소가스 산소 농도",
        "related_tags": [{"tag_name": "BBFIT-520", "description": "유량"}],
    }
    params = _row_params(record)
    assert params["tag_id"] == 10011217
    assert params["tag_name"] == "BBAIT-801"
    # related_tags 는 JSON 문자열로 직렬화된다.
    assert json.loads(params["related_tags"])[0]["tag_name"] == "BBFIT-520"
    # 누락 텍스트 필드는 None.
    assert params["action_guidance"] is None


def test_row_params_requires_tag_id_and_name():
    with pytest.raises(ValueError):
        _row_params({"tag_name": "X"})
    with pytest.raises(ValueError):
        _row_params({"tag_id": 1})
