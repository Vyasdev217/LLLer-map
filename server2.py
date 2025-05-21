from flask import Flask, request, render_template, abort
import requests
import folium
from folium import DivIcon
from pymongo import MongoClient
import pandas as pd
import math

app = Flask(__name__)
logged_ips=set()

client = MongoClient('mongodb://s3:27017/')
db = client['Tsukusi']
collection_access = db['lowlevelaware_access']
collection_country = db['lowlevelaware_country']

def lat_lon_to_vector(latitude, longitude, radius=1.0):
    lat_rad = math.radians(latitude)
    lon_rad = math.radians(longitude)
    x = radius * math.cos(lat_rad) * math.cos(lon_rad)
    y = radius * math.cos(lat_rad) * math.sin(lon_rad)
    z = radius * math.sin(lat_rad)
    return (x, y, z)

def vector_to_lat_lon(x, y, z):
    latitude = math.degrees(math.asin(z))
    longitude = math.degrees(math.atan2(y, x))
    return (latitude, longitude)

def average_lat_lon(lat_lon_list):
    sum_x = sum_y = sum_z = 0.0
    n = len(lat_lon_list)
    for lat, lon in lat_lon_list:
        x, y, z = lat_lon_to_vector(lat, lon)
        sum_x += x
        sum_y += y
        sum_z += z
    avg_x = sum_x / n
    avg_y = sum_y / n
    avg_z = sum_z / n
    return vector_to_lat_lon(avg_x, avg_y, avg_z)

@app.after_request
def add_cache_control(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'  # For HTTP/1.0 compatibility
    return response

@app.route('/favicon.ico')
def favicon():
    abort(404)

@app.before_request
def register():
    if 'X-Forwarded-For' in request.headers:
        client_ip = request.headers['X-Forwarded-For'].split(",")[0]
    else:
        client_ip = request.remote_addr
    print(client_ip)
    ip_data = collection_access.find_one({'ipaddr': client_ip})
    if ip_data is None:
        try:
            response = requests.get(f'https://ipinfo.io/{client_ip}/json')
            response.raise_for_status()
            ip_info = response.json()
            country = ip_info.get('country')
            loc = ip_info.get('loc')
            if country and loc:
                latitude, longitude = map(float, loc.split(','))
                collection_access.insert_one({'ipaddr': client_ip, 'country': country, 'latitude': latitude, 'longitude': longitude})
                country_data = collection_country.find_one({'country': country})
                if country_data is None: collection_country.insert_one({'country': country, 'access_count': 1})
                else: collection_country.update_one({'country': country}, {'$inc': {'access_count': 1}})
        except requests.exceptions.RequestException as e: return {'error': str(e)}, 500

@app.route('/', methods=['GET'])
def flat():
    world_map = folium.Map(location=[20, 0], zoom_start=2, max_bounds=True)
    data = collection_access.find({})
    data = [(item['latitude'], item['longitude']) for item in data]
    for i in data:
        folium.CircleMarker(
            location=(i[0], i[1]),
            radius=1.5,
            color='red',
            fill=True,
            fill_opacity=0.4,
        ).add_to(world_map)


    data = collection_country.find({}, {'country': 1, 'access_count': 1})
    data = [(item['country'], item['access_count']) for item in data]
    df = pd.DataFrame(data, columns=['Country', 'AccessCount'])
    for _, row in df.iterrows():
        avg_latitude = collection_access.aggregate([{ "$match": { "country": row['Country'] } },{"$group": {"_id": None, "avg_latitude": {"$avg": "$latitude"}}}])
        avg_longitude = collection_access.aggregate([{ "$match": { "country": row['Country'] } },{"$group": {"_id": None, "avg_longitude": {"$avg": "$longitude"}}}])
        avg_latitude = list(avg_latitude)[0]['avg_latitude']
        avg_longitude = list(avg_longitude)[0]['avg_longitude']
        folium.Marker(
            location=(avg_latitude, avg_longitude),
            popup=f"{row['Country']}: {row['AccessCount']}"
        ).add_to(world_map)

    data = collection_access.find({}, {'latitude': 1, 'longitude': 1})
    data = [(item['latitude'], item['longitude']) for item in data]
    folium.Marker(
        location=average_lat_lon(data),
        popup='やらないオフ会の場所',
        icon=folium.Icon(color='red')
    ).add_to(world_map)
    world_map.save('templates/heatmap.html')

    return render_template('heatmap.html')

@app.route('/globe', methods=['GET'])
def globe():
    pins = {
        'access': [],
        'country': [],
        'offkai': []
    }
    data = collection_access.find({})
    data = [(item['latitude'], item['longitude']) for item in data]
    for i in data: pins['access'].append({'longitude': i[1], 'latitude': i[0]})

    data = collection_country.find({}, {'country': 1, 'access_count': 1})
    data = [(item['country'], item['access_count']) for item in data]
    df = pd.DataFrame(data, columns=['Country', 'AccessCount'])
    for _, row in df.iterrows():
        avg_latitude = collection_access.aggregate([{ "$match": { "country": row['Country'] } },{"$group": {"_id": None, "avg_latitude": {"$avg": "$latitude"}}}])
        avg_longitude = collection_access.aggregate([{ "$match": { "country": row['Country'] } },{"$group": {"_id": None, "avg_longitude": {"$avg": "$longitude"}}}])
        avg_latitude = list(avg_latitude)[0]['avg_latitude']
        avg_longitude = list(avg_longitude)[0]['avg_longitude']
        pins['country'].append({'longitude': avg_longitude, 'latitude': avg_latitude,'label':f"{row['Country']}: {row['AccessCount']}"})

    return render_template('cesium.html', pins=pins)


if __name__ == '__main__':
    app.run(debug=False, port=6000)
