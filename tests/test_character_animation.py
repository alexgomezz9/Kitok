from types import SimpleNamespace
from PIL import Image
from kitok.dialogue_audio import TimedTurn
from kitok.dialogue_video import DialogueCompositor
from test_dialogue_gameplay import item


def compositor(tmp_path, probability=0):
    for character in ('rick','morty'):
        folder=tmp_path/character;folder.mkdir(exist_ok=True)
        for pose in ('one','two','three'):
            image=Image.new('RGBA',(20,30),(20,40,60,128));image.save(folder/(pose+'.png'))
    return DialogueCompositor(SimpleNamespace(character_root=tmp_path,character_reaction_probability=probability))


def test_active_only_first_frame_and_eased_transitions(tmp_path):
    comp=compositor(tmp_path)
    timeline=[TimedTurn('rick_es',0,3,'Hola Morty'),TimedTurn('morty_es',3.14,6,'Hola Rick')]
    layers=comp._poses(item(),timeline)
    assert len(layers)==2 and all(layer.active for layer in layers)
    assert layers[0].initial and layers[0].start==0 and layers[0].entry_seconds==0
    assert layers[1].entry_seconds>0 and layers[0].exit_seconds>0
    assert 'pow(' in layers[1].y_expression(350)
    assert '-48' in layers[0].x_expression(40,48)
    assert '+(48)' in layers[1].x_expression(40,48)


def test_pose_sequence_is_seeded_nonrepeating_and_has_no_reactions(tmp_path):
    comp=compositor(tmp_path,1)
    turns=[TimedTurn('rick_es' if i%2==0 else 'morty_es',i*6,i*6+5.8,'Some words') for i in range(8)]
    first=comp._poses(item(visual_seed='abc'),turns)
    second=compositor(tmp_path,1)._poses(item(visual_seed='abc'),turns)
    assert first==second
    for speaker in ('rick_es','morty_es'):
        appearances=[layer for layer in first if layer.speaker==speaker]
        assert all(a.asset.path!=b.asset.path for a,b in zip(appearances,appearances[1:]))
    assert all(layer.active for layer in first)
    assert all(not entry['reaction'] for entry in comp.metadata['character_appearances'])


def test_short_turn_has_only_speaker_and_alpha_crop_sets_visible_height(tmp_path):
    comp=compositor(tmp_path,1)
    layers=comp._poses(item(),[TimedTurn('rick_es',0,0.6,'Hola')])
    assert len(layers)==1 and layers[0].active
    workspace=tmp_path/'work';workspace.mkdir()
    cropped=comp.registry.cropped(layers[0].asset,workspace)
    width,height=comp._target_size(cropped,layers[0])
    assert height==round(740*layers[0].scale)
    assert width==round(height*20/30)


def test_first_morty_turn_does_not_add_rick_preview(tmp_path):
    comp=compositor(tmp_path)
    layers=comp._poses(item(),[TimedTurn('morty_es',0,2,'Hola'),TimedTurn('rick_es',2.14,4,'Vale')])
    assert [(layer.speaker, layer.turn_index) for layer in layers] == [('morty_es',0),('rick_es',1)]
    assert layers[0].initial and layers[0].entry_seconds==0
    assert all(layer.active for layer in layers)


def test_repeated_speaker_has_no_duplicate_overlay(tmp_path):
    comp=compositor(tmp_path)
    layers=comp._poses(item(),[TimedTurn('rick_es',0,2,'A'),TimedTurn('rick_es',2.14,4,'B')])
    assert layers[0].end <= layers[1].start
    assert layers[0].exit_seconds==0 and layers[1].entry_seconds==0
    layers=comp._poses(item(),[TimedTurn('morty_es',0,2,'A'),TimedTurn('rick_es',2.14,4,'B')])
    assert len(layers)==2 and [layer.speaker for layer in layers]==['morty_es','rick_es']
