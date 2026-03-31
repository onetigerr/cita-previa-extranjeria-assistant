# Cita Previa Extranjería Monitor

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A web scraper that automates the soul-crushing process of checking for appointment slots (cita previa) at the Spanish immigration office (extranjería).

If you've ever tried to book an appointment, you know the drill: endless refreshing, cryptic error messages, and the sinking feeling that you might be clicking your way into oblivion. This script is your friendly neighborhood robot, tirelessly checking for you so you can reclaim your sanity.

---

## Features

- **Automated Checking**: Runs on a continuous loop to monitor for available appointment slots.
- **Telegram Notifications**: Sends an alert via Telegram the moment a potential slot is found.
- **Intelligent Error Handling**:
  - Only sends Telegram notifications for errors after **5 consecutive failures** (resets on any successful page load).
  - Automatically waits **15-20 minutes** if a "Read timed out" error occurs to avoid WAF blocks.
- **Human-like Behavior**: Uses randomized delays and Firefox profiles to maintain session persistence and reduce bot detection.
- **Customizable**: Configure multiple parameters (province, office, procedure, personal data) via environment variables.

---

## Booking Strategy & Workflow

1. **Background Monitoring**: The script runs in a Firefox browser instance that can stay in the background.
2. **Automatic Selection**: When an appointment slot is detected, the script automatically:
   - Selects the first available office.
   - Fills in your contact information (phone and email).
   - Navigates to the calendar selection page.
3. **Notification**: You receive a Telegram alert immediately.
4. **User Intervention (The 15-Minute Window)**:
   - The script will **pause for 15 minutes** on the calendar page.
   - Simply find the already open Firefox window.
   - Manually select your preferred date and time.
   - Complete the remaining steps, save the confirmation, and print the results!
5. **Success**: Enjoy your appointment!

---

## Prerequisites

- **Python 3.10+**
- **Poetry** (recommended for dependency management)
- **Firefox Browser**: Required for the scraper to run.
  - On macOS, you can install it via Homebrew:
    ```bash
    brew install --cask firefox
    ```

---

## Getting Started

1. **Clone the repository**:
   ```bash
   git clone https://github.com/onetigerr/cita-previa-extranjeria-monitor.git
   cd cita-previa-extranjeria-monitor
   ```

2. **Install dependencies**:
   ```bash
   poetry install
   ```

3. **Configure the environment**:
   Copy the example environment file and fill in your details:
   ```bash
   cp .env.example .env
   # Edit .env with your favorite editor
   ```

4. **Run the monitor**:
   Start the monitor specifying a session ID to keep the browser instance alive across runs:
   ```bash
   SCRAPER_SESSION_ID=my_session poetry run python src/main.py
   ```

---

## Configuration (`.env`)

The scraper uses the following environment variables:

- `SCRAPER_OUTPUT_DIR`: Path for logs and screenshots.
- `TELEGRAM_BOT_TOKEN`: Your API token from @BotFather.
- `TELEGRAM_CHAT_ID`: Your chat ID from @userinfobot.
- `PROVINCE`: The province to search in (e.g., `Valencia`, `Madrid`, `Barcelona`).
- `PROCEDURE`: The exact name of the procedure (trámite) you need.
- `NIE`, `FULL_NAME`, `COUNTRY`: Your personal data for filling out the forms.
- `PHONE_NUMBER`, `EMAIL`: Contact details for the final steps.

---

## Contributing

Contributions are welcome! If you find a bug or have a feature request, please open an issue or submit a pull request.

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

Original code based on: [kpliuta/cita-previa-extranjeria-monitor](https://github.com/kpliuta/cita-previa-extranjeria-monitor)
