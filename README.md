# 📡 Transit Lab Bot | جامع البيانات

Welcome to the **Transit Lab Bot** repository! This bot is designed to help users collect and save GPS tracking data in the form of `.gpx` files and transform this data into a tabular format for storage in a PostgreSQL database. Additionally, it gathers valuable information like fares, vehicle conditions, and bus gathering areas, including official and unofficial stops or terminals.

## 🚀 Features

- **Collect GPS Data**: Save `.gpx` files recorded by users.
- **Transform Data**: Convert `.gpx` data into a tabular format suitable for database storage.
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
    - Create a new database and user for the bot.

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
    python TransitlabBot.py
    ```
2. **Interact with the Bot on Telegram**:
    - Send your `.gpx` file to the bot.
    - Provide additional information as prompted (e.g., fares, vehicle conditions, etc.).


## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 📞 Contact

For any inquiries or support, please reach out to [Omar alqaysi](mailto:omar@transit-labb.com).

