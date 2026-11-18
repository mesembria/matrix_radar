import math, re, pathlib, yaml, jinja2
cfg = yaml.safe_load(open(pathlib.Path(__file__).resolve().parent.parent / 'homeassistant' / 'flight_radar.yaml'))
sensor = cfg['template'][0]['sensor'][0]
tpl_packed = sensor['attributes']['packed']; tpl_state = sensor['state']
home = (39.9936, -105.0897)  # Lafayette, CO approx
def mi_to_ll(east, north): return home[0] + north/69.05, home[1] + east/(69.17*math.cos(math.radians(home[0])))
lat1, lon1 = mi_to_ll(-5.2, 3.1); lat2, lon2 = mi_to_ll(1.0, -0.5); lat3, lon3 = mi_to_ll(0.2, 0.2)
flights = [
 dict(flight_number='UA1482', callsign='UAL1482', aircraft_registration='N37522', aircraft_code='B738', aircraft_model='Boeing 737-8H4', airport_origin_code_iata='DEN', airport_destination_code_iata='SFO', latitude=lat1, longitude=lon1, altitude=23740, heading=270, ground_speed=280, on_ground=0),
 dict(flight_number=None, callsign='N172SP', aircraft_registration='N172SP', aircraft_code='C172', aircraft_model='Cessna 172S Skyhawk SP, with; junk', airport_origin_code_iata=None, airport_destination_code_iata=None, latitude=lat2, longitude=lon2, altitude=6640, heading=315, ground_speed=100, on_ground=0),
 dict(flight_number='', callsign='CGABC', aircraft_registration='C-GABC', aircraft_code='', aircraft_model=None, airport_origin_code_iata='', airport_destination_code_iata='', latitude=lat3, longitude=lon3, altitude=5100, heading=0, ground_speed=0, on_ground=0),
 dict(flight_number='', callsign='', aircraft_registration='N9021B', aircraft_code='BE36', latitude=40.04, longitude=-105.05, altitude=5300, heading=10, ground_speed=0, on_ground=1),
]
env = jinja2.Environment()
env.filters['regex_replace'] = lambda v, find='', rep='': re.sub(find, rep, v)
env.globals.update(cos=math.cos, pi=math.pi)
def state_attr(e, a):
    if e == 'zone.home': return {'latitude': home[0], 'longitude': home[1]}[a]
    return flights if a == 'flights' else None
env.globals['state_attr'] = state_attr
print('state  :', env.from_string(tpl_state).render().strip())
out = env.from_string(tpl_packed).render()
print('packed :', repr(out), len(out))

# ---------- 9th field: aircraft model ----------
recs = {r.split(',')[0]: r.split(',') for r in out.split(';')}
assert all(len(r) == 9 for r in recs.values()), recs
assert recs['UA1482'][8] == 'BOEING 737-8H4', recs['UA1482']
assert recs['N172SP'][8] == 'CESSNA 172S SKYH', recs['N172SP']
assert recs['CGABC'][8] == '', recs['CGABC']
# Worst case size: 40 planes, 7-char ids, 16-char names.
big = [dict(flight_number='UAL1234', aircraft_code='B38M', aircraft_model='X' * 30,
            airport_origin_code_iata='DEN', airport_destination_code_iata='SFO',
            latitude=lat1, longitude=lon1, altitude=23740, heading=270, ground_speed=280, on_ground=0)] * 40
flights[:] = big
big_out = env.from_string(tpl_packed).render()
assert len(big_out) < 2600, len(big_out)
print('model field: OK, worst case', len(big_out), 'chars')

# ---------- Automation that sends the planes to the panel over MQTT ----------
autos = cfg['automation']
assert len(autos) == 1, autos
a = autos[0]
assert a['id'] == 'flight_radar_publish', a['id']
trig = a['triggers']
assert {'trigger': 'state', 'entity_id': 'sensor.flight_radar_planes', 'attribute': 'packed'} in trig, trig
assert {'trigger': 'homeassistant', 'event': 'start'} in trig, trig
assert {'trigger': 'time_pattern', 'seconds': '/30'} in trig, trig  # empty sky never changes state
assert len(a['actions']) == 1
act = a['actions'][0]
assert act['action'] == 'mqtt.publish', act
assert act['data']['topic'] == 'flight_radar/planes'
assert act['data']['retain'] is True
payload = act['data']['payload']
attrs = {'packed': out}
env.globals['state_attr'] = lambda e, k: attrs.get(k) if e == 'sensor.flight_radar_planes' else None
assert env.from_string(payload).render() == out
attrs.clear()
assert env.from_string(payload).render() == ''
text = open(pathlib.Path(__file__).resolve().parent.parent / 'homeassistant' / 'flight_radar.yaml').read()
assert 'number.set_value' not in text
print('automation: OK')
