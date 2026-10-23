"""Offline regression checks; synthetic panels, never operational episode assets."""
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as Args
import unittest
from unittest.mock import patch

from PIL import Image

spec = importlib.util.spec_from_file_location('batches', Path(__file__).with_name('batches.py'))
b = importlib.util.module_from_spec(spec); spec.loader.exec_module(b)


class BatchesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.ep=Path(self.tmp.name)
        Image.new('RGB',(160,90),'green').save(self.ep/'anchor.png')
        self.scenes=[{'id':f'scene_{i:03}', 'image_file':f'imagenes/scene_{i:03}.png',
                      'scene_prompt':f'Unique request {i:03}.', 'visual_description':f'Object {i:03}'} for i in range(12)]
        (self.ep/'plan.json').write_text(json.dumps({'scenes':self.scenes}))
        self.args=Args(plan='plan.json',start='scene_000',count=9,columns=3,batch='test',reference=[],anchor='anchor.png')
        atlas=Image.new('RGB',(480,270))
        for i in range(9):atlas.paste((i*25,200-i*15,30+i*10),(i%3*160,i//3*90,(i%3+1)*160,(i//3+1)*90))
        self.atlas=self.ep/'atlas.png';atlas.save(self.atlas)

    def make(self):
        result=b.plan(self.ep,self.args);b.crop(self.ep,Args(batch='test',atlas=self.atlas,inset=0,source_kind='test_fixture'))
        return Path(result['manifest']),json.loads(Path(result['manifest']).read_text())

    def test_only_selected_prompts_and_exact_pixel_order(self):
        path,data=self.make();prompt=(path.parent/'prompt.txt').read_text()
        self.assertTrue(all(s['scene_prompt'] in prompt for s in self.scenes[:9]))
        self.assertTrue(all(s['scene_prompt'] not in prompt for s in self.scenes[9:]))
        for i,s in enumerate(data['scenes']):
            with Image.open(path.parent/s['crop']) as im:
                self.assertEqual(im.size,(160,90));self.assertEqual(im.getpixel((0,0)),(i*25,200-i*15,30+i*10))
            self.assertEqual(s['id'],self.scenes[i]['id']);self.assertEqual(s['state'],'cropped_unreviewed')

    def test_collision_preflight_and_idempotent_resume(self):
        _,data=self.make();ids=[s['id'] for s in data['scenes']];args=Args(batch='test',ids=ids,reviewer='test fixture',note='synthetic fixture, no editorial claim')
        (self.ep/'imagenes').mkdir();(self.ep/'imagenes/scene_008.png').write_bytes(b'operator')
        with self.assertRaises(ValueError):b.accept(self.ep,args)
        self.assertFalse((self.ep/'imagenes/scene_000.png').exists())
        (self.ep/'imagenes/scene_008.png').unlink();b.accept(self.ep,args);b.accept(self.ep,args)
        self.assertEqual(len(list((self.ep/'imagenes').glob('*.png'))),9)
        with Image.open(self.ep/'imagenes/scene_000.png') as im:self.assertEqual(im.size,(160,90))
        _, latest=b.load_batch(self.ep,'test')
        self.assertEqual(latest['scenes'][0]['native_size'],[160,90])
        self.assertEqual(latest['scenes'][0]['processing'],'native')

    def test_changed_input_and_prompt_rejected(self):
        result=b.plan(self.ep,self.args);folder=Path(result['manifest']).parent
        (folder/'prompt.txt').write_text('changed')
        with self.assertRaises(ValueError):b.load_batch(self.ep,'test')

    def test_path_traversal_and_aliases_rejected(self):
        self.scenes[0]['image_file']='../escape.png';(self.ep/'plan.json').write_text(json.dumps({'scenes':self.scenes}))
        with self.assertRaises(ValueError):b.plan(self.ep,self.args)
        self.scenes[0]['image_file']='imagenes/scene_001.png';(self.ep/'plan.json').write_text(json.dumps({'scenes':self.scenes}))
        with self.assertRaises(ValueError):b.plan(self.ep,self.args)

    def test_partial_last_block_and_duplicate_batch_rejected(self):
        self.args.start='scene_009';self.args.count=3;b.plan(self.ep,self.args)
        with self.assertRaises(ValueError):b.plan(self.ep,self.args)
        folder=b.batch_dir(self.ep,'test');prompt=(folder/'prompt.txt').read_text();self.assertNotIn('CELL 4',prompt)
        self.args.batch='too-many';self.args.count=4
        with self.assertRaises(ValueError):b.plan(self.ep,self.args)

    def test_interrupted_crop_preserves_attempt(self):
        b.plan(self.ep,self.args)
        with patch.object(b, 'write_json', side_effect=OSError('interrupted')):
            with self.assertRaises(OSError):
                b.crop(self.ep,Args(batch='test',atlas=self.atlas,inset=0,source_kind='test_fixture'))
        saved=(b.batch_dir(self.ep,'test')/'atlas.png').read_bytes()
        Image.new('RGB',(480,270),'red').save(self.atlas)
        with self.assertRaises(ValueError):
            b.crop(self.ep,Args(batch='test',atlas=self.atlas,inset=0,source_kind='test_fixture'))
        self.assertEqual((b.batch_dir(self.ep,'test')/'atlas.png').read_bytes(),saved)

    def test_validator_failure_before_any_publication(self):
        self.make()
        with patch('kitok.youtube_stickman_es.images.ImageBatch.inspect', side_effect=ValueError('40MP limit')):
            with self.assertRaises(ValueError):
                b.accept(self.ep,Args(batch='test',ids=['scene_000'],reviewer='fixture',note='synthetic'))
        self.assertFalse((self.ep/'imagenes').exists())

    def test_failed_publish_exposes_no_partial_output(self):
        self.make()
        with patch.object(b.os, 'link', side_effect=OSError('ENOSPC')):
            with self.assertRaises(OSError):
                b.accept(self.ep,Args(batch='test',ids=['scene_000'],reviewer='fixture',note='synthetic'))
        self.assertFalse((self.ep/'imagenes/scene_000.png').exists())
        b.accept(self.ep,Args(batch='test',ids=['scene_000'],reviewer='fixture',note='synthetic'))
        with Image.open(self.ep/'imagenes/scene_000.png') as im:im.verify()

    def test_duplicate_candidates_and_no_automatic_acceptance(self):
        Image.new('RGB',(480,270),'white').save(self.atlas);_,data=self.make()
        self.assertTrue(any(w.get('exact') for w in data['warnings']))
        self.assertFalse((self.ep/'imagenes').exists())


if __name__=='__main__':unittest.main()
