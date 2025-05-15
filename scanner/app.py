import sqlite3
from flask import Flask, render_template, g

app = Flask(__name__, static_folder='img', static_url_path='/img') # UPDATED LINE

DATABASE = "advertisement_db.db" # Path to your database file

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row # Access columns by name
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

@app.route('/')
def show_latest_image():
    image_name = None
    error_message = None
    sensor_value_display = "N/A"

    try:
        db = get_db()
        cursor = db.cursor()
        # Fetch the sensor_value from the most recent advertisement
        cursor.execute("SELECT sensor_value FROM advertisements ORDER BY timestamp DESC LIMIT 1")
        row = cursor.fetchone()

        if row:
            sensor_value = row['sensor_value']
            if sensor_value is not None:
                # Convert sensor_value to integer for image naming (e.g., 17.0 -> 17)
                image_name = str(int(sensor_value))
                sensor_value_display = image_name
            else:
                error_message = "No sensor value found in the latest DB entry."
        else:
            error_message = "No advertisements found in the database."

    except sqlite3.Error as e:
        error_message = f"Database error: {e}"
    except Exception as e:
        error_message = f"An unexpected error occurred: {e}"

    # Render the HTML page, passing the image name (or None) and any error
    return render_template('index.html', image_name=image_name, error_message=error_message, sensor_value=sensor_value_display)

if __name__ == '__main__':
    # Make sure your images (e.g., 17.png) are in a folder structure like: static/img/17.png
    app.run(debug=True, host='0.0.0.0') # Accessible on your localhost