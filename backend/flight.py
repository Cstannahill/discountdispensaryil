"""Read JSON/text records from observed React Flight data without executing JS."""
from html.parser import HTMLParser
import json
import re


class FlightError(ValueError):
    pass


class _Scripts(HTMLParser):
    def __init__(self,text):
        super().__init__(convert_charrefs=False)
        self.scripts=[];self.active=False;self.buffer=[];self.feed(text)
    def handle_starttag(self,tag,attrs):
        if tag=='script':self.active=True;self.buffer=[]
    def handle_endtag(self,tag):
        if tag=='script' and self.active:
            self.scripts.append(''.join(self.buffer));self.active=False
    def handle_data(self,data):
        if self.active:self.buffer.append(data)


def stream(text):
    if not text.lstrip().startswith('<'):return text
    chunks=[];decoder=json.JSONDecoder()
    for script in _Scripts(text).scripts:
        offset=0
        while True:
            start=script.find('self.__next_f.push(',offset)
            if start<0:break
            start+=len('self.__next_f.push(')
            try:value,end=decoder.raw_decode(script[start:])
            except ValueError as exc:raise FlightError('Malformed Flight script record') from exc
            offset=start+end
            if isinstance(value,list) and len(value)>1 and value[0]==1 and isinstance(value[1],str):chunks.append(value[1])
    return ''.join(chunks)


def records(text):
    data=stream(text).encode('utf-8');offset=0;result={}
    while offset<len(data):
        while offset<len(data) and data[offset:offset+1] in (b'\n',b'\r'):offset+=1
        if offset>=len(data):break
        header=re.match(rb'([0-9a-fA-F]+):T([0-9a-fA-F]+),',data[offset:])
        if header:
            size=int(header[2],16);start=offset+header.end();end=start+size
            if end>len(data):raise FlightError('Truncated Flight text record')
            try:raw=data[start:end].decode('utf-8')
            except UnicodeError as exc:raise FlightError('Invalid UTF-8 Flight text length') from exc
            try:value=json.loads(raw)
            except ValueError:value=raw
            result[header[1].decode().lower()]=value;offset=end
            continue
        end=data.find(b'\n',offset)
        if end<0:end=len(data)
        row=data[offset:end];offset=end+1
        if row.startswith(b':H'):continue  # Unnumbered preload hints.
        match=re.match(rb'([0-9a-fA-F]+):(.*)',row)
        if not match:raise FlightError('Malformed Flight row boundary')
        try:value=json.loads(match[2])
        except ValueError:continue  # Import/style/hint records are not JSON models.
        result[match[1].decode().lower()]=value
    return result


def resolve(value,models,seen=()):
    if value=='$undefined':return None
    if not isinstance(value,str) or not re.fullmatch(r'\$[0-9a-fA-F]+(?::[^:]+)*',value):return value
    if value in seen:raise FlightError('Cyclic Flight reference')
    key,*path=value[1:].split(':')
    if key.lower() not in models:raise FlightError('Missing Flight model '+key)
    current=models[key.lower()]
    for segment in path:
        current=resolve(current,models,seen+(value,))
        if isinstance(current,dict) and segment in current:current=current[segment]
        elif isinstance(current,list) and segment=='props' and len(current)==4 and current[0]=='$':current=current[3]
        elif isinstance(current,list) and segment.isdigit() and int(segment)<len(current):current=current[int(segment)]
        else:raise FlightError('Flight reference path does not exist')
    return resolve(current,models,seen+(value,))
