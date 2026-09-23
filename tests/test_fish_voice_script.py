from unittest.mock import Mock

from pydantic import SecretStr

from kitok import voice_tests as test_fish_voices


def test_parse_custom_voice_for_repeatable_cli_use():
    voice = test_fish_voices.parse_voice("My New Voice=reference-123")

    assert voice.slug == "my_new_voice"
    assert voice.name == "My New Voice"
    assert voice.reference_id == "reference-123"


def test_voice_test_uses_same_parameters_and_both_variants(tmp_path):
    client = Mock()
    factory = Mock(return_value=client)
    settings = Mock(
        fish_api_key=SecretStr("test-key"),
        fish_model="s2.1-pro-free",
        fish_tts_timeout_seconds=180,
    )
    voice = test_fish_voices.VoiceChoice("new_voice", "New Voice", "ref-id")

    generated, failures = test_fish_voices.generate_voice_tests(
        (voice,),
        tmp_path,
        settings=settings,
        client_factory=factory,
    )

    assert failures == []
    assert generated == [tmp_path / "new_voice_plain.mp3", tmp_path / "new_voice_tags.mp3"]
    assert client.synthesize.call_count == 2
    for call in client.synthesize.call_args_list:
        assert call.kwargs == {
            "speed": 0.95,
            "temperature": 0.8,
            "top_p": 0.7,
            "normalize_loudness": True,
        }
    assert client.synthesize.call_args_list[0].args[0] == test_fish_voices.PLAIN_TEXT
    assert client.synthesize.call_args_list[1].args[0] == test_fish_voices.TAGGED_TEXT
    client.close.assert_called_once_with()
