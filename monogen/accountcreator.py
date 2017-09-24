import time

from random import randint
from datetime import datetime, timedelta

from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from seleniumrequests import Chrome, PhantomJS

from .jibber import *
from .ptcexceptions import *
from .url import *

BASE_URL = "https://club.pokemon.com/us/pokemon-trainer-club"

# endpoints taken from PTCAccount
SUCCESS_URLS = (
    'https://club.pokemon.com/us/pokemon-trainer-club/parents/email',  # This initially seemed to be the proper success redirect
    'https://club.pokemon.com/us/pokemon-trainer-club/sign-up/',  # but experimentally it now seems to return to the sign-up, but still registers
)

# As both seem to work, we'll check against both success destinations until I have I better idea for how to check success
DUPE_EMAIL_URL = 'https://club.pokemon.com/us/pokemon-trainer-club/forgot-password?msg=users.email.exists'
BAD_DATA_URL = 'https://club.pokemon.com/us/pokemon-trainer-club/parents/sign-up'


def _random_string():
    return generate_words(3)

def _random_password():
    return generate_password()


def _random_birthday():
    start = datetime(1970, 1, 1)
    end = datetime(2000, 12, 31)
    diff = end - start
    random_duration = randint(0, diff.total_seconds())
    birthday = start + timedelta(seconds=random_duration)
    return birthday.strftime('%Y-%m-%d')


def _validate_birthday(user_birthday):
    # raises PTCInvalidBirthdayException if invalid
    # split by -
    # has to be at least 2002 and after 1918
    # char length 10
    try:
        birthday = datetime.strptime(user_birthday, '%Y-%m-%d')

        # Check year is between 1918 and 2002, and also that it's a valid date
        assert datetime(year=1918, month=1, day=1) <= birthday <= datetime(year=2002, month=12, day=31)
    except (AssertionError, ValueError):
        raise PTCInvalidBirthdayException("Invalid birthday!")
    else:
        return True


def _validate_password(password):
    # Check that password length is between 8 and 50 characters long
    if len(password) < 8 or len(password) > 50:
        raise PTCInvalidPasswordException('Password must be between 8 and 50 characters.')


def _validate_username(driver, username):
    try:
        response = driver.request('POST','https://club.pokemon.com/api/signup/verify-username', data={"name": username})
        response_data = response.json()

        if response_data['valid'] and not response_data['inuse']:
            print("User '{}' is available, proceeding...".format(username))
        else:
            print("User '{}' is already in use.".format(username))
            driver.quit()
            raise PTCInvalidNameException("User '{}' is already in use.".format(username))
    except Exception:
        print("Failed to check if the username is available!")


def create_account(username, password, email, birthday, captchakey2, captchatimeout):
    if password:
        _validate_password(password)

    print("Attempting to create user {user}:{pw}. Opening browser...".format(user=username, pw=password))
    if captchakey2:
        dcap = dict(DesiredCapabilities.PHANTOMJS)
        dcap["phantomjs.page.settings.userAgent"] = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/57.0.2987.98 Safari/537.36'
        driver = PhantomJS(desired_capabilities=dcap)
    else:
        driver = Chrome()
        driver.set_window_size(600, 600)

    # Input age: 1992-01-08
    print("Step 1: Verifying age using birthday:", birthday)
    driver.get("{}/sign-up/".format(BASE_URL))
    assert driver.current_url == "{}/sign-up/".format(BASE_URL)
    elem = driver.find_element_by_name("dob")

    # Workaround for different region not having the same input type
    driver.execute_script("var input = document.createElement('input'); input.type='text'; input.setAttribute('name', 'dob'); arguments[0].parentNode.replaceChild(input, arguments[0])", elem)

    elem = driver.find_element_by_name("dob")
    elem.send_keys(birthday)
    elem.submit()

    # Create account page
    print("Step 2: Entering account details")
    assert driver.current_url == "{}/parents/sign-up".format(BASE_URL)

    user = driver.find_element_by_name("username")
    user.clear()
    user.send_keys(username)

    _validate_username(driver, username)

    elem = driver.find_element_by_name("password")
    elem.clear()
    elem.send_keys(password)

    elem = driver.find_element_by_name("confirm_password")
    elem.clear()
    elem.send_keys(password)

    elem = driver.find_element_by_name("email")
    elem.clear()
    elem.send_keys(email)

    elem = driver.find_element_by_name("confirm_email")
    elem.clear()
    elem.send_keys(email)

    element = driver.find_element_by_id("id_public_profile_opt_in_1")
    driver.execute_script("arguments[0].scrollIntoView(true);", element)
    element.click()


    element = driver.find_element_by_name("terms")
    driver.execute_script("arguments[0].scrollIntoView(true);", element)
    element.click()

    if not captchakey2:
        #Do manual captcha entry
        print("You did not pass a 2captcha key. Please solve the captcha manually.")
        elem = driver.find_element_by_class_name("g-recaptcha")
        driver.execute_script("arguments[0].scrollIntoView(true);", elem)
        # Waits 90 seconds for you to input captcha
        try:
            WebDriverWait(driver, 90).until(EC.text_to_be_present_in_element_value((By.NAME, "g-recaptcha-response"), ""))
            print("Captcha successful.")
        except TimeoutException:
            print("Timed out while manually solving captcha")
    else:
        # Now to automatically handle captcha
        print("Starting autosolve recaptcha")
        html_source = driver.page_source
        gkey_index = html_source.find("https://www.google.com/recaptcha/api2/anchor?k=") + 47
        gkey = html_source[gkey_index:gkey_index+40]
        recaptcharesponse = "Failed"
        while(recaptcharesponse == "Failed"):
            recaptcharesponse = openurl("http://2captcha.com/in.php?key=" + captchakey2 + "&method=userrecaptcha&googlekey=" + gkey + "&pageurl=" + driver.current_url)
        captchaid = recaptcharesponse[3:]
        recaptcharesponse = "CAPCHA_NOT_READY"
        elem = driver.find_element_by_class_name("g-recaptcha")
        print("We will wait 10 seconds for captcha to be solved by 2captcha")
        start_time = time.monotonic()
        timedout = False
        while recaptcharesponse == "CAPCHA_NOT_READY":
            time.sleep(10)
            elapsedtime = time.monotonic() - start_time
            if elapsedtime > captchatimeout:
                print("Captcha timeout reached. Exiting.")
                timedout = True
                break
            print("Captcha still not solved, waiting another 10 seconds.")
            recaptcharesponse = "Failed"
            while(recaptcharesponse == "Failed"):
                recaptcharesponse = openurl("http://2captcha.com/res.php?key={}&action=get&id={}".format(captchakey2, captchaid))
        if timedout == False:
            solvedcaptcha = recaptcharesponse[3:]
            elem = driver.find_element_by_name("g-recaptcha-response")
            elem = driver.execute_script("arguments[0].style.display = 'block'; return arguments[0];", elem)
            elem.send_keys(solvedcaptcha)
            print("Solved captcha")
    try:
        user.submit()
    except StaleElementReferenceException:
        print("Error StaleElementReferenceException!")

    try:
        _validate_response(driver)
    except Exception:
        print("Failed to create user:", username)
        driver.quit()
        raise

    print("Account successfully created.")
    driver.quit()
    return True


def _validate_response(driver):
    url = driver.current_url
    if url in SUCCESS_URLS:
        return True
    elif url == DUPE_EMAIL_URL:
        raise PTCInvalidEmailException("Email already in use.")
    elif url == BAD_DATA_URL:
        if "Enter a valid email address." in driver.page_source:
            raise PTCInvalidEmailException("Invalid email.")
        else:
            raise PTCInvalidNameException("Username already in use.")
    else:
        raise PTCException("Generic failure. User was not created.")


def random_account(email, username=None, password=None, birthday=None, plusmail=True, recaptcha=None, captchatimeout=1000):
    try_username = username if username else _random_string()
    password = password if password else _random_password()
    captchakey2 = recaptcha
    if plusmail:
        pm = email.split("@")
        email = pm[0] + "+" + try_username + "@" + pm[1]
    if birthday:
        _validate_birthday(birthday)
        try_birthday = str(birthday)
    else:
        try_birthday = _random_birthday()

    account_created = False
    while not account_created:
        try:
            account_created = create_account(try_username, password, email, try_birthday, captchakey2, captchatimeout)
        except PTCInvalidNameException:
            if username is None:
                try_username = _random_string()
                if plusmail:
                    email = pm[0] + "+" + try_username + "@" + pm[1]
            else:
                raise

    return {
        'username': try_username,
        'password': password,
        'email': email,
        'provider': 'ptc'
    }
