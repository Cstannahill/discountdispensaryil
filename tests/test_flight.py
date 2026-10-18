import json
import unittest
from backend.flight import records,resolve,FlightError


class FlightTests(unittest.TestCase):
    def test_split_scripts_and_utf8_length_delimited_records_with_embedded_newlines(self):
        text=json.dumps({'name':'Café 🌿','description':'first\nsecond'},ensure_ascii=False)
        raw=':HL["/style.css","style"]\na:T'+format(len(text.encode()),'x')+','+text+'\nb:{"data":"$a"}\n'
        html=''.join('<script>self.__next_f.push('+json.dumps([1,part])+')</script>' for part in (raw[:18],raw[18:]))
        models=records(html)
        self.assertEqual(resolve(models['b']['data'],models)['name'],'Café 🌿')

    def test_react_props_reference_paths_are_data_access_only(self):
        models=records('a:[null,["$","$L1",null,{"state":{"queries":[{"state":{"data":{"count":20}}}]}}]]\nb:"$a:1:props:state:queries:0:state:data"\n')
        self.assertEqual(resolve(models['b'],models),{'count':20})

    def test_truncated_lengths_cycles_and_missing_paths_are_errors(self):
        with self.assertRaises(FlightError):records('1:T10,short')
        with self.assertRaises(FlightError):resolve('$a',{'a':'$a'})
        with self.assertRaises(FlightError):resolve('$a:missing',{'a':{}})
