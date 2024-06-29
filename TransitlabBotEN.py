import logging
import os
from datetime import datetime
import psycopg2
from psycopg2 import extras
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv
import gpxpy
from shapely.geometry import Point, LineString
from simplification.cutil import simplify_coords_vw
import pandas as pd
from sqlalchemy import create_engine
import itertools
import boto3

# Load environment variables
load_dotenv()

# Database connection
db_host = os.getenv('DB_HOST')
db_port = os.getenv('DB_PORT')
db_user = os.getenv('DB_USER')
db_password = os.getenv('DB_PASSWORD')
db_name = os.getenv('DB_NAME')

conn = psycopg2.connect(
    host=db_host,
    port=db_port,
    user=db_user,
    password=db_password,
    dbname=db_name
)

engine = create_engine(f'postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}')
# Configure S3
# s3_client = boto3.client('s3')
# s3_bucket_name = ''

# Read the token from the environment variable
TOKEN = os.getenv('BOT_TOKEN')

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Global variables
user_data = {}
video_path = os.path.join(os.path.dirname(__file__), 'intro_480p.mp4')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("🚌 Record Bus Route", callback_data='record_bus_route')],
        [InlineKeyboardButton("🚏 Record Bus Stop", callback_data='record_bus_stop')],
        [InlineKeyboardButton("🎥 Watch Intro Video", callback_data='show_video')],
        [InlineKeyboardButton("❓ Help", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    welcome_message = (
        "👋 <b>Welcome to the Data Collector Bot!</b>\n"
        "What would you like to do now?"
    )
    await update.message.reply_text(welcome_message, reply_markup=reply_markup, parse_mode='HTML')

async def show_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if os.path.exists(video_path):
        with open(video_path, 'rb') as video_file:
            await context.bot.send_video(chat_id=query.message.chat_id, video=video_file, caption="To return to the main menu, press /start")
    else:
        await context.bot.send_message(chat_id=query.message.chat_id, text="The video is not available. Please try again later.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "❓ Help:\n"
        "1. <b>🚌 Record Bus Route:</b> Record the bus route using a GPS tracking app, where the route is recorded when boarding and the recording ends when alighting, then send the tracking file to the bot to save the information.\n"
        "2. <b>🚏 Record Bus Stop:</b> Use this option to record the starting location of the bus from the garage or bus gathering places."
    )
    await update.message.reply_text(help_text, parse_mode='HTML')

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    logging.info(f"Button pressed: {query.data} by user {user_id}")

    if query.data == 'show_video':
        await show_video(update, context)
        return

    if query.data == 'record_bus_route':
        user_data[user_id] = {'step': 'phone_type', 'username': query.from_user.username, 'session_id': datetime.now().strftime("%Y%m%d%H%M%S")}
        keyboard = [
            [InlineKeyboardButton("📱 iPhone", callback_data='phone_iphone')],
            [InlineKeyboardButton("📱 Android", callback_data='phone_android')],
            [InlineKeyboardButton("✅ I have installed the app", callback_data='phone_installed')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "To record the bus route, you need to install the tracking app and run it. Then send the tracking file to the bot to save the information.\n<b>What type of phone do you use?</b>",
            reply_markup=reply_markup, parse_mode='HTML'
        )

    elif query.data in ['phone_iphone', 'phone_android']:
        keyboard = [
            [InlineKeyboardButton("✅ Done", callback_data='phone_installed')],
            [InlineKeyboardButton("❌ Cancel", callback_data='cancel')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        app_link = "https://apps.apple.com/app/id984503772" if query.data == 'phone_iphone' else "https://play.google.com/store/apps/details?id=com.ilyabogdanovich.geotracker"
        await query.edit_message_text(f"Please install the app from the following link:\n{app_link}", reply_markup=reply_markup)

    elif query.data == 'phone_installed':
        user_data[user_id]['step'] = 'upload_gpx'
        await query.edit_message_text("📂 Start recording the journey with the app and do not forget to mark a point when any passenger boards or alights if possible. After finishing, please send the GPX file of the recorded route using the tracking app.")

    elif query.data == 'record_bus_stop':
        user_data[user_id] = {'step': 'vehicle_type_stop', 'session_id': datetime.now().strftime("%Y%m%d%H%M%S"), 'username': query.from_user.username}
        keyboard = [
            [InlineKeyboardButton("🚐 Kia", callback_data='vehicle_kia_stop')],
            [InlineKeyboardButton("🚍 Coaster", callback_data='vehicle_coaster_stop')],
            [InlineKeyboardButton("🚌 Bus", callback_data='vehicle_bus_stop')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("What type of public transport are you going to use?", reply_markup=reply_markup)

    elif query.data == 'help':
        await help_command(query, context)

    elif query.data == 'cancel':
        user_data[user_id]['last_step'] = user_data[user_id]['step']  # Store the current step
        keyboard = [
            [InlineKeyboardButton("✅ Yes", callback_data='confirm_cancel')],
            [InlineKeyboardButton("❌ No", callback_data='deny_cancel')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("❌ Are you sure you want to cancel?", reply_markup=reply_markup)

    elif query.data == 'confirm_cancel':
        await mark_session_as_canceled(user_id)
        user_data.pop(user_id, None)
        await query.edit_message_text("Canceled! Please press /start to return to the main menu.", reply_markup=InlineKeyboardMarkup([]))

    elif query.data == 'deny_cancel':
        # Resume from the last step
        if user_id in user_data and 'last_step' in user_data[user_id]:
            step = user_data[user_id]['last_step']
            if step == 'upload_gpx':
                await query.edit_message_text("📂 Start recording the journey with the app and do not forget to mark a point when any passenger boards or alights if possible. After finishing, please send the GPX file of the recorded route using the tracking app.")
            elif step == 'vehicle_type':
                keyboard = [
                    [InlineKeyboardButton("🚐 Kia", callback_data='vehicle_kia')],
                    [InlineKeyboardButton("🚍 Coaster", callback_data='vehicle_coaster')],
                    [InlineKeyboardButton("🚌 Bus", callback_data='vehicle_bus')],
                    [InlineKeyboardButton("❌ Cancel", callback_data='cancel')]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text("What type of public transport are you going to use?", reply_markup=reply_markup)
            elif step == 'source':
                await query.edit_message_text("🗺️ Enter the departure location (e.g., Alawi, Bab Al-Moatham, Bayaa, etc.):")
            elif step == 'destination':
                await query.edit_message_text("🗺️ Enter the destination (where is the bus going?):")
            elif step == 'enter_fare':
                await query.edit_message_text("💬 Enter the fare manually (numbers only without currency):")
            elif step == 'vehicle_type_stop':
                keyboard = [
                    [InlineKeyboardButton("🚐 Kia", callback_data='vehicle_kia_stop')],
                    [InlineKeyboardButton("🚍 Coaster", callback_data='vehicle_coaster_stop')],
                    [InlineKeyboardButton("🚌 Bus", callback_data='vehicle_bus_stop')]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text("What type of public transport are you going to use?", reply_markup=reply_markup)
            elif step == 'destination_bus_stop':
                await query.edit_message_text("🗺️ Enter the destination (where is the bus going?):")
            # Restore the original step
            user_data[user_id]['step'] = user_data[user_id].pop('last_step')

    elif query.data.startswith('fare_'):
        if user_id not in user_data:
            logging.error(f"Missing user data for user {user_id} when selecting fare")
            return
        fare = query.data.split('_')[1]
        if fare == 'other':
            user_data[user_id]['step'] = 'enter_fare'
            await query.edit_message_text("💬 Enter the fare manually (numbers only without currency):")
        else:
            user_data[user_id]['fare'] = fare
            await ask_vehicle_condition(user_id, context)

    elif query.data.startswith('condition_'):
        vehicle_condition = query.data.split('condition_')[1]
        if user_id in user_data and 'fare' in user_data[user_id] and 'session_id' in user_data[user_id]:
            user_data[user_id]['vehicle_condition'] = vehicle_condition
            await save_all_data(user_id)
            await query.edit_message_text("Fare and vehicle condition recorded. Thank you! Press /start to return to the main menu.", reply_markup=InlineKeyboardMarkup([]))
        else:
            logging.error(f"Missing session data for user {user_id}")

    elif query.data in ['vehicle_kia', 'vehicle_coaster', 'vehicle_bus']:
        vehicle_type = query.data.split('_')[1]
        user_data[user_id]['vehicle_type'] = vehicle_type.capitalize()
        user_data[user_id]['step'] = 'source'
        await query.edit_message_text("🗺️ Enter the departure location (e.g., Alawi, Bab Al-Moatham, Bayaa, etc.):")

    elif query.data in ['vehicle_kia_stop', 'vehicle_coaster_stop', 'vehicle_bus_stop']:
        vehicle_type = query.data.split('_')[1]
        user_data[user_id]['vehicle_type'] = vehicle_type.capitalize()
        user_data[user_id]['step'] = 'destination_bus_stop'
        await query.edit_message_text("🗺️ Enter the destination (where is the bus going?):")

async def ask_vehicle_condition(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("😡 Very Bad", callback_data='condition_very_bad')],
        [InlineKeyboardButton("😟 Bad", callback_data='condition_bad')],
        [InlineKeyboardButton("🙂 Good", callback_data='condition_good')],
        [InlineKeyboardButton("😃 Very Good", callback_data='condition_very_good')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=user_id, text="🚐 How was the condition of the vehicle (what is your overall rating of the car)?", reply_markup=reply_markup)

async def mark_session_as_canceled(user_id: int) -> None:
    logging.info(f"Marking session as canceled for user {user_id}")
    session_id = user_data[user_id]['session_id']
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE bus_routes
            SET cancel = TRUE
            WHERE user_id = %s AND session_id = %s
            """, (user_id, session_id)
        )
        conn.commit()

async def save_fare(user_id: int) -> None:
    try:
        current_time = datetime.now()
        session_id = user_data[user_id]['session_id']
        username = user_data[user_id]['username']
        source = user_data[user_id].get('source', 'unknown')
        destination = user_data[user_id].get('destination', 'unknown')
        fare = user_data[user_id]['fare']
        vehicle_condition = user_data[user_id]['vehicle_condition']
        vehicle_type = user_data[user_id]['vehicle_type']

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO fares (user_id, telegram_username, session_id, date, time, source, destination, fare, vehicle_condition, vehicle_type)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (user_id, username, session_id, current_time.date(), current_time.time(), source, destination, fare, vehicle_condition, vehicle_type)
            )
            conn.commit()
        logging.info("Fare data saved to the database")
    except Exception as e:
        conn.rollback()  # Rollback the transaction in case of error
        logging.error(f"Error saving fare data: {e}")

async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    text = update.message.text

    logging.info(f"User choice: {text} by user {user_id}")

    if user_id not in user_data:
        user_data[user_id] = {'session_id': datetime.now().strftime("%Y%m%d%H%M%S"), 'username': update.message.from_user.username}

    if user_id in user_data and user_data[user_id]['step'] == 'source':
        user_data[user_id]['source'] = text
        user_data[user_id]['step'] = 'destination'
        await update.message.reply_text("🗺️ Enter the destination (where is the bus going?):")

    elif user_id in user_data and user_data[user_id]['step'] == 'destination':
        user_data[user_id]['destination'] = text
        await ask_fare(user_id, context)

    elif user_data[user_id]['step'] == 'enter_fare':
        user_data[user_id]['fare'] = text
        await ask_vehicle_condition(user_id, context)

    elif user_id in user_data and user_data[user_id]['step'] == 'destination_bus_stop':
        user_data[user_id]['destination'] = text
        user_data[user_id]['step'] = 'location_bus_stop'
        keyboard = [
            [KeyboardButton("📍 Share Location", request_location=True)],
            ["❌ Cancel"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("Please share your location to save the bus stop.", reply_markup=reply_markup)

    elif text == "❌ Cancel":
        keyboard = [
            [InlineKeyboardButton("✅ Yes", callback_data='confirm_cancel')],
            [InlineKeyboardButton("❌ No", callback_data='deny_cancel')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("❌ Are you sure you want to cancel?", reply_markup=reply_markup)

async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    if user_id not in user_data:
        await update.message.reply_text("Please select from the menu.")
        return

    current_time = datetime.now()
    lat, lon = update.message.location.latitude, update.message.location.longitude

    if user_data[user_id].get('step') == 'location_bus_stop':
        session_id = user_data[user_id]['session_id']
        vehicle_type = user_data[user_id]['vehicle_type']
        username = user_data[user_id]['username']

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO bus_stops (user_id, telegram_username, session_id, vehicle_type, date, time, destination, lat, lon, cancel)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (user_id, username, session_id, vehicle_type, current_time.date(), current_time.time(), user_data[user_id]['destination'], lat, lon, False)
            )
            conn.commit()

        user_data.pop(user_id, None)
        await update.message.reply_text("The bus stop has been saved. Thank you! Press /start to return to the main menu.", reply_markup=ReplyKeyboardRemove())

def chunked_iterable(iterable, size):
    it = iter(iterable)
    while chunk := list(itertools.islice(it, size)):
        yield chunk

def simplify_route(route_points, tolerance=0.000000001):
    line = LineString(route_points)
    simplified = simplify_coords_vw(line.coords, tolerance)
    return list(simplified)

def get_route_points(session_id, point_type):
    query = """
        SELECT lon, lat, time, telegram_username, date, source, destination, cancel
        FROM bus_routes
        WHERE session_id = %s AND point_type = %s
        ORDER BY time
    """
    df = pd.read_sql(query, engine, params=(session_id, point_type))
    return df

def save_to_simplified_table(user_id, username, vehicle_type, session_id, source, destination, simplified_points):
    logging.info("Inside save_to_simplified_table")
    line_geom = LineString(simplified_points).wkt

    single_row = (
        session_id,
        user_id,
        username,
        vehicle_type,
        datetime.now().date(),
        datetime.now().time(),
        source,
        destination,
        False,
        line_geom
    )

    insert_query = """
        INSERT INTO simplified_bus_routes (session_id, user_id, telegram_username, vehicle_type, date, time, source, destination, cancel, geom_line)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, ST_SetSRID(ST_GeomFromText(%s), 4326))
    """

    with conn.cursor() as cur:
        cur.execute(insert_query, single_row)
        conn.commit()

    logging.info("Exiting save_to_simplified_table")

async def gpx_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    if user_id not in user_data or user_data[user_id].get('step') != 'upload_gpx':
        await update.message.reply_text("Please select from the menu.")
        return

    # Download the GPX file
    file = await context.bot.get_file(update.message.document.file_id)
    session_id = user_data[user_id]['session_id']
    username = user_data[user_id]['username']
    current_date = datetime.now().strftime("%Y%m%d")
    file_name = f'{username}_{session_id}_{current_date}.gpx'
    file_path = os.path.join(os.getcwd(), file_name)
    await file.download_to_drive(file_path)

    try:
        # Upload the file to S3
        s3_key = f'gpx-files/{file_name}'
        s3_client.upload_file(file_path, s3_bucket_name, s3_key)
        logging.info(f"GPX file uploaded to S3 at {s3_key}")
    except Exception as e:
        logging.error(f"Error uploading to s3: {e}")

    try:
        # Initialize gpx_data dictionary
        user_data[user_id]['gpx_data'] = {
            'tracks': [],
            'waypoints': []
        }

        # Parse the GPX file
        with open(file_path, 'r') as gpx_file:
            gpx = gpxpy.parse(gpx_file)

        logging.info("GPX file parsed successfully")

        point_id = 1

        for track in gpx.tracks:
            for segment in track.segments:
                for point in segment.points:
                    user_data[user_id]['gpx_data']['tracks'].append({
                        'lat': point.latitude,
                        'lon': point.longitude,
                        'time': point.time,
                        'type': 'bus_routing'
                    })
                    point_id += 1

        point_id = 1
        for waypoint in gpx.waypoints:
            user_data[user_id]['gpx_data']['waypoints'].append({
                'lat': waypoint.latitude,
                'lon': waypoint.longitude,
                'time': waypoint.time,
                'type': 'passenger_on_off'
            })
            point_id += 1

        await ask_vehicle_type(user_id, context)
    except Exception as e:
        logging.error(f"Error processing GPX file: {e}")
        await update.message.reply_text("An error occurred while processing the GPX file. Please try again.")

async def ask_fare(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [
            InlineKeyboardButton("💵 250", callback_data='fare_250'),
            InlineKeyboardButton("💵 500", callback_data='fare_500')
        ],
        [
            InlineKeyboardButton("💵 750", callback_data='fare_750'),
            InlineKeyboardButton("💵 1000", callback_data='fare_1000')
        ],
        [
            InlineKeyboardButton("💵 1250", callback_data='fare_1250'),
            InlineKeyboardButton("💵 1500", callback_data='fare_1500')
        ],
        [
            InlineKeyboardButton("💵 2000", callback_data='fare_2000'),
            InlineKeyboardButton("💬 Other", callback_data='fare_other')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=user_id, text="💵 What was the fare?", reply_markup=reply_markup)

async def ask_vehicle_type(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("🚐 Kia", callback_data='vehicle_kia')],
        [InlineKeyboardButton("🚍 Coaster", callback_data='vehicle_coaster')],
        [InlineKeyboardButton("🚌 Bus", callback_data='vehicle_bus')],
        [InlineKeyboardButton("❌ Cancel", callback_data='cancel')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=user_id, text="What type of public transport are you going to use?", reply_markup=reply_markup)

async def save_all_data(user_id: int) -> None:
    try:
        if 'source' not in user_data[user_id] or 'destination' not in user_data[user_id] or 'vehicle_type' not in user_data[user_id]:
            logging.info("Not all necessary data is available yet. Waiting for user input.")
            return
        session_id = user_data[user_id]['session_id']
        username = user_data[user_id]['username']
        source = user_data[user_id].get('source', 'unknown')
        destination = user_data[user_id].get('destination', 'unknown')
        vehicle_type = user_data[user_id]['vehicle_type']
        fare = user_data[user_id]['fare']
        vehicle_condition = user_data[user_id]['vehicle_condition']

        tracks = user_data[user_id]['gpx_data']['tracks']
        waypoints = user_data[user_id]['gpx_data']['waypoints']

        with conn.cursor() as cur:
            track_values = [
                (
                    user_id, username, session_id, vehicle_type, point_id,
                    track['time'].date(), track['time'].time(), source, destination,
                    track['lat'], track['lon'], 'bus_routing', False
                ) for point_id, track in enumerate(tracks, start=1)
            ]

            waypoint_values = [
                (
                    user_id, username, session_id, vehicle_type, point_id,
                    waypoint['time'].date(), waypoint['time'].time(), source, destination,
                    waypoint['lat'], waypoint['lon'], 'passenger_on_off', False
                ) for point_id, waypoint in enumerate(waypoints, start=1)
            ]

            sql_query = """
                INSERT INTO bus_routes (user_id, telegram_username, session_id, vehicle_type, point_id, date, time, source, destination, lat, lon, point_type, cancel)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            extras.execute_batch(cur, sql_query, track_values + waypoint_values)

            cur.execute(
                """
                INSERT INTO fares (user_id, telegram_username, session_id, date, time, source, destination, fare, vehicle_condition, vehicle_type)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (user_id, username, session_id, datetime.now().date(), datetime.now().time(), source, destination, fare, vehicle_condition, vehicle_type)
            )

            conn.commit()

        track_update_values = [
            (Point(track['lon'], track['lat']).wkt, session_id, track['lat'], track['lon'])
            for track in tracks
        ]
        waypoint_update_values = [
            (Point(waypoint['lon'], waypoint['lat']).wkt, session_id, waypoint['lat'], waypoint['lon'])
            for waypoint in waypoints
        ]

        track_update_query = """
            UPDATE bus_routes
            SET geom_point = ST_SetSRID(ST_GeomFromText(%s), 4326)
            WHERE session_id = %s AND point_type = 'bus_routing' AND lat = %s AND lon = %s
        """
        waypoint_update_query = """
            UPDATE bus_routes
            SET geom_point = ST_SetSRID(ST_GeomFromText(%s), 4326)
            WHERE session_id = %s AND point_type = 'passenger_on_off' AND lat = %s AND lon = %s
        """

        with conn.cursor() as cur:
            extras.execute_batch(cur, track_update_query, track_update_values)
            extras.execute_batch(cur, waypoint_update_query, waypoint_update_values)
            conn.commit()

        df = get_route_points(session_id, 'bus_routing')
        route_points = list(zip(df['lon'], df['lat']))
        simplified_points = simplify_route(route_points)
        logging.info("Calling save_to_simplified_table...")
        save_to_simplified_table(user_id, username, vehicle_type, session_id, source, destination, simplified_points)
        logging.info("save_to_simplified_table called successfully")
        logging.info("All data saved to the database")
    except Exception as e:
        conn.rollback()
        logging.error(f"Error saving all data: {e}")

def main() -> None:
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_choice))
    application.add_handler(MessageHandler(filters.LOCATION, location_handler))
    application.add_handler(MessageHandler(filters.Document.FileExtension("gpx"), gpx_handler))

    logging.getLogger('httpx').setLevel(logging.WARNING)

    application.run_polling()

if __name__ == '__main__':
    main()
