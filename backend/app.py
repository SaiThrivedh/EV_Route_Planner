from flask import Flask, request, jsonify
from flask_cors import CORS
import requests

app = Flask(__name__)
CORS(app)

OSRM_URL = 'https://router.project-osrm.org/route/v1/driving'
OPENCHARGEMAP_URL = 'https://api.openchargemap.io/v3/poi/'


def get_osrm_route(start, end, alternatives=False):
    s = f"{start[1]},{start[0]}"
    e = f"{end[1]},{end[0]}"
    url = f"{OSRM_URL}/{s};{e}?overview=full&geometries=geojson&alternatives={'true' if alternatives else 'false'}"
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    return r.json()


@app.route('/route')
def route():
    start_raw = request.args.get('start')
    end_raw = request.args.get('end')
    if not start_raw or not end_raw:
        return jsonify({'error': 'missing start or end'}), 400

    try:
        s_lat, s_lon = map(float, start_raw.split(','))
        e_lat, e_lon = map(float, end_raw.split(','))
    except Exception:
        return jsonify({'error': 'bad start/end format; expected lat,lon'}), 400

    blocked = request.args.get('blocked', 'false').lower() == 'true'

    try:
        osrm = get_osrm_route((s_lat, s_lon), (e_lat, e_lon), alternatives=True)
    except Exception as ex:
        return jsonify({'error': 'routing error', 'detail': str(ex)}), 500

    routes = osrm.get('routes', [])
    if not routes:
        return jsonify({'error': 'no routes found'}), 404

    chosen = routes[0]
    if blocked and len(routes) > 1:
        chosen = routes[1]

    def to_json(rt):
        return {
            'distance_m': rt['distance'],
            'duration_s': rt['duration'],
            'geometry': rt['geometry']
        }

    return jsonify({
        'chosen': to_json(chosen),
        'primary': to_json(routes[0]),
        'alternative': to_json(routes[1]) if len(routes) > 1 else None,
        'blocked_simulated': blocked
    })


@app.route('/stations')
def stations():
    lat = request.args.get('lat')
    lon = request.args.get('lon')
    if not lat or not lon:
        return jsonify({'error': 'lat,lon required'}), 400

    params = {
        'latitude': lat,
        'longitude': lon,
        'distance': 100,  # larger radius for better coverage
        'distanceunit': 'KM',
        'maxresults': 25,
        'output': 'json',
        'key': 'd6087db3-4b7b-4a87-8f95-fdb7331188e3'  # ✅ your real API key
    }

    headers = {
        'User-Agent': 'EVRoutePlanner/1.0 (https://evroute.local)'
    }

    try:
        r = requests.get(OPENCHARGEMAP_URL, params=params, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()
    except Exception as ex:
        print("Station lookup error:", ex)
        return jsonify({'error': 'station lookup failed', 'detail': str(ex)}), 500

    if not isinstance(data, list) or not data:
        return jsonify({'stations': []})

    simplified = [
        {
            'id': p.get('ID'),
            'title': p.get('AddressInfo', {}).get('Title'),
            'lat': p.get('AddressInfo', {}).get('Latitude'),
            'lon': p.get('AddressInfo', {}).get('Longitude'),
            'address': p.get('AddressInfo', {}).get('AddressLine1')
        }
        for p in data
        if p.get('AddressInfo', {}).get('Latitude') and p.get('AddressInfo', {}).get('Longitude')
    ]

    return jsonify({'stations': simplified})


@app.route('/geocode')
def geocode():
    place = request.args.get('place')
    if not place:
        return jsonify({'error': 'missing place'}), 400

    url = "https://nominatim.openstreetmap.org/search"
    params = {'q': place, 'format': 'json', 'limit': 1}
    try:
        r = requests.get(url, params=params, headers={'User-Agent': 'EVRoutePlanner/1.0'})
        r.raise_for_status()
        results = r.json()
    except Exception as ex:
        return jsonify({'error': 'geocoding failed', 'detail': str(ex)}), 500

    if not results:
        return jsonify({'error': 'not found'}), 404

    lat = float(results[0]['lat'])
    lon = float(results[0]['lon'])
    return jsonify({'lat': lat, 'lon': lon})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
