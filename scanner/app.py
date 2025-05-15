from flask import Flask, jsonify
import sqlite3

app = Flask(__name__)
DATABASE = 'log_db.db'  # Path to your SQLite database
DEFAULT_IMAGE = 'img/Slike/default.png' # Adjust path if necessary

def get_latest_sensor_data():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT sensor_value FROM log_db.db ORDER BY timestamp DESC LIMIT 1")
    result = cursor.fetchone()
    conn.close()
    if result:
        return result[0]
    return None

@app.route('/api/latest_data')
def latest_data():
    sensor_value = get_latest_sensor_data()
    if sensor_value is not None:
        return jsonify({'sensor_value': sensor_value})
    return jsonify({'error': 'No sensor data available'}), 404

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0') # Make it accessible on your network