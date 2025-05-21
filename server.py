from flask import Flask, request, redirect, url_for, render_template, abort
import requests
import folium
import pandas as pd
from collections import defaultdict

app = Flask(__name__)
logged_ips=set()
access_counts = defaultdict(lambda: [0, 0, 0])

@app.route('/favicon.ico')
def favicon():
    abort(404)

@app.route('/', methods=['GET'])
def index():
    if 'X-Forwarded-For' in request.headers:
        client_ip = request.headers['X-Forwarded-For'].split(",")[0]
    else:
        client_ip = request.remote_addr
    print(client_ip)
    if client_ip not in logged_ips:
        try:
            response = requests.get(f'https://ipinfo.io/{client_ip}/json')
            response.raise_for_status()
            ip_info = response.json()
            country = ip_info.get('country')
            loc = ip_info.get('loc')
            print(client_ip, country, loc)
            if country and loc:
                access_counts[country][0] += 1
                latitude, longitude = map(float, loc.split(','))
                access_counts[country][1] = (access_counts[country][1]*(access_counts[country][0]-1)+latitude)/access_counts[country][0]
                access_counts[country][2] = (access_counts[country][2]*(access_counts[country][0]-1)+longitude)/access_counts[country][0]
            logged_ips.add(client_ip)
        except requests.exceptions.RequestException as e:
            return {'error': str(e)}, 500

    data = [(country, count[0], count[1], count[2]) for country, count in access_counts.items()]
    df = pd.DataFrame(data, columns=['Country', 'AccessCount', 'Latitude', 'Longitude'])

    world_map = folium.Map(location=[20, 0], zoom_start=2)

    for _, row in df.iterrows():
        folium.CircleMarker(
            location=(row['Latitude'], row['Longitude']),
            radius=row['AccessCount'] * 0.3,
            color='blue',
            fill=True,
            fill_opacity=0.6,
            popup=f"{row['Country']}: {row['AccessCount']} accesses"
        ).add_to(world_map)

    world_map.save('templates/index.html')

    return render_template('index.html')


@app.route('/heatmap', methods=['GET'])
def heatmap():
    data = [(country, count[0], count[1], count[2]) for country, count in access_counts.items()]
    df = pd.DataFrame(data, columns=['Country', 'AccessCount', 'Latitude', 'Longitude'])

    world_map = folium.Map(location=[20, 0], zoom_start=2, max_bounds=True)

    for _, row in df.iterrows():
        folium.CircleMarker(
            location=(row['Latitude'], row['Longitude']),
            radius=row['AccessCount'] * 0.1,
            color='blue',
            fill=True,
            fill_opacity=0.6,
            popup=f"{row['Country']}: {row['AccessCount']} accesses"
        ).add_to(world_map)

    world_map.save('templates/heatmap.html')

    return render_template('heatmap.html')

if __name__ == '__main__':
    app.run(debug=True)
