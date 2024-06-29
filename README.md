# 📡 Transit Lab Bot | بوت جامع البيانات 

Welcome to the **Transit Lab Bot** repository! This bot is designed to help users collect and save GPS tracking data in the form of `.gpx` files and transform this data into a tabular format for storage in a PostgreSQL database. Additionally, it gathers valuable information like fares, vehicle conditions, and bus gathering areas, including official and unofficial stops or terminals.  
We found the need for this tool to help us gather information on official and unofficial public transportation means.
This tool is mainly used by our volunteers & contributors.  

The bot is available in Both **English & Arabic** Languages.

## 🚀 Features

- **Collect GPS Data**: Save `.gpx` files recorded by users.
- **Transform Data**: Convert `.gpx` data into a tabular format suitable for database storage.
- **Simplify the gpx file** by reducing the number of points while maintaining the overall polyline shape.
- **Save to PostgreSQL**: Store the processed data in a PostgreSQL database.
- **Gather Additional Information**: Collect details about fares, vehicle conditions, and bus gathering areas.

## 🛠️ Tech Stack

- **Language**: Python 3.10 🐍
- **Database**: PostgreSQL 🐘
- **Telegram Bot API**: Facilitates interaction with users 📲

## 📦 Installation

1. **Clone the Repository**:
    ```bash
    git clone https://github.com/Transit-lab-Baghdad/Bus-routes-collector-bot.git
    ```
2. **Navigate to the Project Directory**:
    ```bash
    cd Bus-routes-collector-bot
    ```
3. **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
4. **Set Up PostgreSQL**:
    - Ensure you have PostgreSQL installed and running.
    - Create a new database, User, Tables using the following SQL script:
```sql
CREATE DATABASE bot_db;
CREATE USER bot_user WITH ENCRYPTED PASSWORD 'password';
GRANT ALL PRIVILEGES ON DATABASE bot_db TO bot_user;
CREATE TABLE bus_routes (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    telegram_username VARCHAR(255),
    session_id VARCHAR(255),
    vehicle_type VARCHAR(50),
    point_id INT,
    date DATE,
    time TIME,
    source VARCHAR(255),
    destination VARCHAR(255),
    lat DOUBLE PRECISION,
    lon DOUBLE PRECISION,
    point_type VARCHAR(50),
    cancel BOOLEAN DEFAULT FALSE,
    geom_point GEOMETRY(Point, 4326)
);

CREATE TABLE bus_stops (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    telegram_username VARCHAR(255),
    session_id VARCHAR(255),
    vehicle_type VARCHAR(50),
    date DATE,
    time TIME,
    destination VARCHAR(255),
    lat DOUBLE PRECISION,
    lon DOUBLE PRECISION,
    cancel BOOLEAN DEFAULT FALSE
);

CREATE TABLE fares (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    telegram_username VARCHAR(255),
    session_id VARCHAR(255),
    date DATE,
    time TIME,
    source VARCHAR(255),
    destination VARCHAR(255),
    fare INT,
    vehicle_condition VARCHAR(50),
    vehicle_type VARCHAR(50)
);

CREATE TABLE simplified_bus_routes (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(255),
    user_id BIGINT NOT NULL,
    telegram_username VARCHAR(255),
    vehicle_type VARCHAR(50),
    date DATE,
    time TIME,
    source VARCHAR(255),
    destination VARCHAR(255),
    cancel BOOLEAN DEFAULT FALSE,
    geom_line GEOMETRY(LineString, 4326)
);
```


5. **Configure Environment Variables**:
    - Create a `.env` file in the project directory.
    - Add your Telegram Bot API token (provided by Bot Father from Telegram) and PostgreSQL connection details to the `.env` file:
    ```
    DB_HOST=your_database_host_link
    DB_PORT=your_db_port
    DB_USER=your_username
    DB_PASSWORD=your_database_password
    DB_NAME=your_database_name
    BOT_TOKEN=your_telegram_bot_token
    ```

## 🚀 Usage

1. **Run the Bot**:
    ```bash
    python TransitlabBotEN.py
    ```
2. **Interact with the Bot on Telegram**:
    - Send your `.gpx` file to the bot.
    - Provide additional information as prompted (e.g., fares, vehicle conditions, etc.).
  
## Bot Workflow

<img src="https://github.com/Transit-lab-Baghdad/Bus-routes-collector-bot/assets/116530009/301dabda-5dc5-4ed2-8cbd-e5e783847979" alt="Workflow" width="500" height="1000">



## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 📞 Contact

For any inquiries or support, please reach out to [Omar alqaysi](mailto:omar@transit-labb.com).

