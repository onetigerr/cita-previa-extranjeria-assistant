"""
Entry point for the Cita Previa Extranjeria Monitor.
"""
import os
from datetime import datetime
from typing import List, Dict, Any, Callable

from selenium import webdriver
from selenium.webdriver.common.by import By
from termux_web_scraper.error_hook import ScreenshotErrorHook, NotificationErrorHook, ErrorHook
from termux_web_scraper.helpers import select_option_by_text, random_sleep, click_element, send_keys, \
    get_optional_element, save_screenshot
from termux_web_scraper.notifier import TelegramNotifier, Notifier
from termux_web_scraper.scraper_builder import ScraperBuilder, get_default_driver_options

from config import SCRAPER_OUTPUT_DIR, TELEGRAM_API_URL, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, PROVINCE, OFFICE, \
    PROCEDURE, NIE, FULL_NAME, COUNTRY, SCRAPER_SESSION_ID, PHONE_NUMBER, EMAIL


class URLRejectedError(Exception):
    """Exception raised when the URL is rejected by the administrator (WAF/F5)."""
    pass


class ConsecutiveNotificationErrorHook(ErrorHook):
    """
    An error hook that only sends a notification after a certain threshold 
    of consecutive errors is reached.
    """

    def __init__(self, threshold: int = 5):
        self.threshold = threshold
        self.counter = 0

    def handle(self, exception: Exception, driver: webdriver.Firefox, notifiers: List[Notifier]):
        """
        Increment the counter and send notifications only if the threshold is met.
        """
        self.counter += 1
        print(f"ConsecutiveNotificationErrorHook: Consecutive error #{self.counter}. Threshold: {self.threshold}")
        
        if self.counter >= self.threshold:
            message = f"Cita Previa Extranjeria Monitor: [CRITICAL] {self.threshold} consecutive errors reached. Latest error: {exception}"
            print(f"ConsecutiveNotificationErrorHook: Threshold reached. Sending notification.")
            for notifier in notifiers:
                notifier.notify(message)
            # Not resetting the counter here; we reset only on success.
            # This means it will keep notifying for error 6, 7... until a success happens.
            # OR, should it only notify ONCE at 5?
            # User said: "А если пять ошибок накопилось, то только тогда отправлять мне сообщение"
            # It usually means "at 5 and possibly every time after".
            # Let's keep it this way for now.

    def reset(self):
        """
        Resets the consecutive error counter to 0.
        """
        if self.counter > 0:
            print(f"ConsecutiveNotificationErrorHook: SUCCESS! Resetting error counter (was {self.counter}).")
        self.counter = 0


def check_for_rejection(driver):
    """
    Checks if the current page contains the 'URL rejected' message.
    If found, raises URLRejectedError.
    """
    try:
        # Check if the rejection message is in the page source
        # "The requested URL was rejected. Please consult with your administrador."
        if "The requested URL was rejected" in driver.page_source:
            return True
    except Exception:
        pass
    return False


def main():
    """
    Main function to run the Cita Previa Extranjeria Monitor.

    This function configures the scraper with defined steps and error hooks, and then runs the scraping process.
    """
    startup_time: str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"Starting up at: {startup_time}")

    # Set up Firefox options with profile if session ID is provided
    from selenium.webdriver.firefox.options import Options
    options = Options()
    options.accept_insecure_certs = True
    
    # Ignore certificate authenticity errors and security blocks
    options.set_preference("network.stricttransportsecurity.preloadlist", False)
    options.set_preference("security.cert_pinning.enforcement_level", 0)
    options.set_preference("security.enterprise_roots.enabled", True)
    options.set_preference("security.tls.version.min", 1)
    options.set_preference("security.ssl.enable_ocsp_stapling", False)
    options.set_preference("security.ssl.enable_ocsp_must_staple", False)
    options.set_preference("security.OCSP.enabled", 0)
    options.set_preference("browser.xul.error_pages.expert_bad_cert", True)
    
    if SCRAPER_SESSION_ID:
        profile_dir = os.path.join(SCRAPER_OUTPUT_DIR, "sessions", SCRAPER_SESSION_ID)
        os.makedirs(profile_dir, exist_ok=True)
        options.add_argument("-profile")
        options.add_argument(profile_dir)
        print(f"Using Firefox profile for session '{SCRAPER_SESSION_ID}' at: {profile_dir}")

    # Build and run the application using the framework
    consecutive_error_hook = ConsecutiveNotificationErrorHook(threshold=5)
    
    scraper = (
        ScraperBuilder()
        .with_driver_options(options)
        .with_notifier(
            TelegramNotifier(
                api_url=TELEGRAM_API_URL,
                bot_token=TELEGRAM_BOT_TOKEN,
                chat_id=TELEGRAM_CHAT_ID
            ))
        .with_error_hook(ScreenshotErrorHook(os.path.join(SCRAPER_OUTPUT_DIR, "screenshots")))
        .with_error_hook(consecutive_error_hook)
        .with_state({'consecutive_errors': consecutive_error_hook})
        .with_step("Navigating to the appointment website", navigate_to_website)
        .with_step("Select Province", select_province)
        .with_step("Select Office and Procedure", select_office_and_procedure)
        .with_step("Navigate through warning page", navigate_through_warning_page)
        .with_step("Fill in Personal Data", fill_in_personal_data)
        .with_step("Request Appointment", request_appointment)
        .with_step("Verify Response", verify_response)
        .with_step("Extract Available Offices", extract_available_offices)
        .with_step("Fill Contact Information", fill_contact_info)
        .with_step("Calendar Step", calendar_step)
        .build()
    )

    import atexit
    original_quit = scraper.driver.quit
    atexit.register(original_quit)
    scraper.driver.quit = lambda: print("--- Iteration over. Keeping browser open for the next loop... ---")

    print("\nStarting continuous monitoring loop. Press Ctrl+C to stop.")
    while True:
        try:
            scraper.run()
        except KeyboardInterrupt:
            print("Stopping monitor...")
            break
        except URLRejectedError:
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] CRITICAL: Access rejected by administrator.")
            print("Waiting 15-20 minutes before restarting process...")
            # 15 to 20 minutes: 900,000 to 1,200,000 ms
            random_sleep(900000, 1200000)
            print("Restarting after rejection wait...")
        except Exception as e:
            # error_hooks in scraper.run() already handled the exception (screenshot/notification)
            err_msg = str(e)
            if "Read timed out" in err_msg:
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] ERROR: Read timed out detected.")
                print("Waiting 15-20 minutes as requested...")
                # 15 to 20 minutes: 900,000 to 1,200,000 ms
                random_sleep(900000, 1200000)
                continue

            if check_for_rejection(scraper.driver):
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] CRITICAL: Access rejected by administrator (detected during error recovery).")
                print("Waiting 15-20 minutes before restarting process...")
                random_sleep(900000, 1200000)
                continue
                
            handle_error_recovery(scraper.driver)
            print("Restarting process after error...")
            random_sleep(30000, 90000)

def handle_error_recovery(driver):
    """
    Checks if there's an error page with a 'Volver', 'Aceptar', or 'Enviar' button.
    If found, saves a screenshot and clicks the button to reset state.
    """
    if check_for_rejection(driver):
        # Let the main loop handle the 15-20 min wait and restart
        return

    try:
        for btn_id in ["btnVolver", "btnAceptar", "btnEnviar"]:
            btn = get_optional_element(driver, (By.ID, btn_id), timeout=2)
            if btn:
                print(f"Timeout or missing elements. '{btn_id}' button detected.")
                save_screenshot(driver, os.path.join(SCRAPER_OUTPUT_DIR, "screenshots"))
                print(f"Clicking '{btn_id}' to reset state...")
                click_element(driver, (By.ID, btn_id), timeout=2)
                random_sleep(3000, 6000)
                return
    except Exception as e:
        print(f"Error while attempting recovery via recovery buttons: {e}")

def navigate_to_website(driver, state, notify):
    driver.get('https://icp.administracionelectronica.gob.es/icpco/index')
    if check_for_rejection(driver):
        raise URLRejectedError()
    
    # Successfully navigated
    state['consecutive_errors'].reset()


def select_province(driver, state, notify):
    if check_for_rejection(driver):
        raise URLRejectedError()
    
    # Wait for the form longer (up to 30 sec), as the Cloudflare/F5 verification page is loading
    try:
        select_option_by_text(driver, (By.NAME, 'form'), PROVINCE, timeout=30)
        random_sleep(9000, 15000)
    except Exception as e:
        print(f"Failed to select province: {e}")
        raise # Re-raise to trigger error hooks and stop sequence
        
    try:
        click_element(driver, (By.ID, "btnAceptar"))
        # Successfully interacted
        state['consecutive_errors'].reset()
    except Exception as e:
        print(f"Failed to click Aceptar button: {e}")
        raise


def select_office_and_procedure(driver, state, notify):
    if check_for_rejection(driver):
        raise URLRejectedError()

    if OFFICE:
        try:
            select_option_by_text(driver, (By.NAME, 'sede'), OFFICE)
            random_sleep(3000, 6000)
        except Exception as e:
            print(f"Failed to select office: {e}")
            raise

    if PROCEDURE:
        try:
            try:
                select_option_by_text(driver, (By.NAME, 'tramiteGrupo[0]'), PROCEDURE, timeout=5)
            except Exception:
                print("Failed to select trámite in tramiteGrupo[0]. Trying tramiteGrupo[1]...")
                select_option_by_text(driver, (By.NAME, 'tramiteGrupo[1]'), PROCEDURE)
        except Exception as e:
            print(f"Failed to select procedure: {e}")
            raise
            
        random_sleep(9000, 15000)

    try:
        driver.execute_script("envia()")
        state['consecutive_errors'].reset()
    except Exception as e:
        print(f"Failed to execute envia(): {e}")
        raise


def navigate_through_warning_page(driver, state, notify):
    if check_for_rejection(driver):
        raise URLRejectedError()

    random_sleep(9000, 15000)
    try:
        driver.execute_script("document.forms[0].submit()")
        state['consecutive_errors'].reset()
    except Exception as e:
        print(f"Failed to submit form on warning page: {e}")
        raise


def fill_in_personal_data(driver, state, notify):
    if check_for_rejection(driver):
        raise URLRejectedError()

    try:
        send_keys(driver, (By.NAME, "txtIdCitado"), NIE)
        random_sleep(3000, 6000)
    except Exception as e:
        print(f"Failed to fill NIE: {e}")
        raise
        
    try:
        send_keys(driver, (By.NAME, "txtDesCitado"), FULL_NAME)
        random_sleep(3000, 6000)
    except Exception as e:
        print(f"Failed to fill name: {e}")
        raise

    if COUNTRY:
        try:
            select_option_by_text(driver, (By.NAME, 'txtPaisNac'), COUNTRY)
            random_sleep(9000, 15000)
        except Exception as e:
            print(f"Failed to select country: {e}")
            raise

    try:
        driver.execute_script("envia()")
        state['consecutive_errors'].reset()
    except Exception as e:
        print(f"Failed to execute envia() on personal data page: {e}")
        raise


def request_appointment(driver, state, notify):
    if check_for_rejection(driver):
        raise URLRejectedError()

    random_sleep(9000, 15000)
    try:
        driver.execute_script("enviar('solicitud')")
        state['consecutive_errors'].reset()
    except Exception as e:
        print(f"Failed to click solicitar: {e}")
        raise


def verify_response(driver, state, notify):
    if check_for_rejection(driver):
        raise URLRejectedError()

    error_message_element = get_optional_element(driver, (By.CLASS_NAME, "mf-msg__info"))
    if error_message_element and 'En este momento no hay citas disponibles' in error_message_element.text:
        state['appointment_found'] = False
        print("No appointment slots available at the moment...")
        
        # We reached this point, so it's a "successful" run even if no slots found
        state['consecutive_errors'].reset()

        print("Waiting 4 to 7 minutes before exiting to mimic human behavior...")
        random_sleep(240000, 420000) # 4 to 7 minutes in milliseconds
        
        print("Clicking 'Salir' button...")
        click_element(driver, (By.ID, "btnSalir"))
    else:
        state['appointment_found'] = True
        print("Appointment slot found!")


def extract_available_offices(driver, state, notify):
    if check_for_rejection(driver):
        raise URLRejectedError()

    if not state.get('appointment_found', False):
        return

    offices_text = ""
    has_office_select = False
    offices_found = False
    
    try:
        sede_select = get_optional_element(driver, (By.ID, "idSede"), timeout=2)
        if sede_select:
            has_office_select = True
            from selenium.webdriver.support.ui import Select
            select_element = Select(sede_select)
            valid_options = [opt for opt in select_element.options if opt.get_attribute("value")]
            
            if valid_options:
                offices_found = True
                options_text = [opt.text.strip() for opt in valid_options]
                offices_text = "\n\nAvailable locations:\n- " + "\n- ".join(options_text)
                
                # Automatically select the first available office to proceed
                first_value = valid_options[0].get_attribute("value")
                select_element.select_by_value(first_value)
                print(f"Automatically selected first office: {valid_options[0].text.strip()}")

                # Notify ONLY if we found specific locations
                notify(f"Cita Previa Extranjeria Monitor: Appointment slot found!{offices_text}")
                save_screenshot(driver, os.path.join(SCRAPER_OUTPUT_DIR, "screenshots"))
                
    except Exception as e:
        print(f"Failed to extract and select office locations: {e}")

    if not offices_found:
        print("No specific office locations found in the dropdown. Treating as no appointment found...")
        state['appointment_found'] = False
        print("Waiting 4 to 7 minutes before exiting to mimic human behavior...")
        random_sleep(240000, 420000) # 4 to 7 minutes in milliseconds
        
        print("Clicking 'Salir' button...")
        try:
            click_element(driver, (By.ID, "btnSalir"), timeout=2)
        except:
            pass
        return

    # Consistent with earlier stages: click the next button / submit
    if has_office_select:
        random_sleep(3000, 6000)
        driver.execute_script("enviar()")
        state['consecutive_errors'].reset()


def fill_contact_info(driver, state, notify):
    """
    Fills in the phone number and email address on the contact information page.
    """
    if check_for_rejection(driver):
        raise URLRejectedError()

    if not state.get('appointment_found', False):
        return

    print("Filling in contact information...")
    try:
        send_keys(driver, (By.ID, "txtTelefonoCitado"), PHONE_NUMBER)
        random_sleep(2000, 4000)
    except Exception as e:
        print(f"Failed to fill phone number: {e}")

    try:
        send_keys(driver, (By.ID, "emailUNO"), EMAIL)
        random_sleep(2000, 4000)
    except Exception as e:
        print(f"Failed to fill email (primary): {e}")

    try:
        send_keys(driver, (By.ID, "emailDOS"), EMAIL)
        random_sleep(2000, 4000)
    except Exception as e:
        print(f"Failed to fill email (confirmation): {e}")

    try:
        # User specified to call enviar()
        driver.execute_script("enviar()")
        state['consecutive_errors'].reset()
        random_sleep(9000, 15000)
    except Exception as e:
        print(f"Failed to execute enviar() on contact info page: {e}")
        raise


def calendar_step(driver, state, notify):
    """
    Step for the calendar page. Parses available dates and notifies the user.
    """
    if check_for_rejection(driver):
        raise URLRejectedError()

    if not state.get('appointment_found', False):
        return

    print("Parsing calendar for available dates...")
    try:
        # Extract month and year
        month_el = get_optional_element(driver, (By.CLASS_NAME, "ui-datepicker-month"), timeout=5)
        year_el = get_optional_element(driver, (By.CLASS_NAME, "ui-datepicker-year"), timeout=5)
        
        if month_el and year_el:
            month = month_el.text.strip()
            year = year_el.text.strip()
            
            # Find all clickable days (<a> tags in the calendar table)
            day_elements = driver.find_elements(By.CSS_SELECTOR, ".ui-datepicker-calendar a")
            available_days = [day.text.strip() for day in day_elements]
            
            if available_days:
                days_str = ", ".join(available_days)
                message = f"Cita Previa Extranjeria Monitor: Available dates found!\n\nCalendar: {month} {year}\nDays: {days_str}"
                print(f"Dates found: {month} {year} - {days_str}")
                notify(message)
                state['consecutive_errors'].reset()
            else:
                print(f"Calendar page reached ({month} {year}), but no selectable days found.")
                notify(f"Cita Previa Extranjeria Monitor: Calendar page reached ({month} {year}), but no specific days seem selectable.")
                state['consecutive_errors'].reset()
        else:
            print("Failed to locate month/year elements on calendar page.")
            notify("Cita Previa Extranjeria Monitor: Calendar page reached, but failed to parse month/year.")
            state['consecutive_errors'].reset()

    except Exception as e:
        print(f"Error parsing calendar: {e}")
        # Notifying the user about the error so they know they are on the calendar page
        notify(f"Cita Previa Extranjeria Monitor: Error reached calendar page but failed to parse dates automatically.")
        state['consecutive_errors'].reset()

    print("Waiting 15 minutes as requested...")
    # 15 minutes = 900,000 ms
    random_sleep(900000, 900000)


if __name__ == "__main__":
    main()
