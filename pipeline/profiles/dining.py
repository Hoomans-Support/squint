"""The dining sample (a food ordering and table booking app). SYNTHETIC.

Same internal ids as the wallet (screens, personas, products, journeys); only the words and a few business numbers differ.
Amounts stay in PHP. The wallet defaults live in schema.py and build_results.py.
"""

SCREEN_LABELS = {
    "prices": "Menu", "welcome": "Welcome", "register_phone": "Sign up: phone number", "otp": "OTP code",
    "personal_data": "Name", "tin": "Dietary preferences", "kyc_selfie": "Payment method", "register_done": "Signed up",
    "login_phone": "Login: phone number", "home": "Home", "wallet": "Restaurant picker", "topup_amount": "Party size and deposit",
    "topup_confirm": "Booking confirm", "topup_done": "Booking done", "product_list": "Choose a dish category", "txn_details": "Cart",
    "txn_checkout": "Checkout and payment", "txn_done": "Order placed",
}
JOURNEY_LABELS = {"browse": "Browse the menu", "register": "Sign up", "login": "Login", "topup": "Table booking", "transaction": "Order food"}
PERSONA_LABELS = {"unregistered": "Guests", "large_business": "Office groups", "sari_sari": "Students", "individual_trader": "Families",
                  "individual": "Couples or solo", "unknown": "Unknown", "fraudster": "Promo abusers"}
PRODUCT_LABELS = {"eload": "Rice meals", "water_bill": "Noodles and soups", "electricity_bill": "Burgers and fries", "game_voucher": "Pizza",
                  "cable_internet": "Coffee and tea", "send_money": "Group platters", "postpaid_telecom": "Desserts"}

# The payment method is asked after sign-up, when a deposit is due, so it sits inside the table booking path (not sign-up).
JOURNEYS = {
    "register": ["welcome", "register_phone", "otp", "personal_data", "tin", "register_done"],
    "topup": ["wallet", "topup_amount", "kyc_selfie", "topup_confirm", "topup_done"],
}

UI_STEPS = {
    "register_login": [("prices", ["prices"], "Browse menu"), ("welcome", ["welcome"], "App open"),
                       ("phone", ["register_phone", "login_phone"], "Phone number"), ("otp", ["otp"], "OTP code"),
                       ("personal_data", ["personal_data"], "Name"), ("tin", ["tin"], "Dietary preferences"),
                       ("done", ["register_done", "home"], "Signed in")],
    "topup": [("wallet", ["wallet"], "Pick a restaurant"), ("amount", ["topup_amount"], "Party size and deposit"),
              ("kyc_selfie", ["kyc_selfie"], "Add payment method"),
              ("confirm", ["topup_confirm"], "Confirm booking"), ("done", ["topup_done"], "Booking confirmed")],
    "transaction": [("product", ["product_list"], "Choose a dish category"), ("details", ["txn_details"], "Cart"),
                    ("confirm", ["txn_checkout"], "Checkout and payment"), ("done", ["txn_done"], "Order placed")],
}
UI_JOURNEY_NAMES = {"register_login": "Sign up and login", "topup": "Table booking", "transaction": "Order food"}

VALUE_PER_SESSION = {"register_login": 120, "topup": 150, "transaction": 250}   # ASSUMPTIONS, not data
VALUE_ASSUMPTION = ("Assumed value: placeholder values per completed task (PHP 120 sign-up or login, PHP 150 table booking, PHP 250 order). "
                    "Not measured; replace with real figures before quoting pesos.")

ELEMENT_LABELS = {"resend": "Resend code / receive via SMS", "verify": "Verify button", "pay": "Pay now button", "continue": "Continue button",
                  "submit": "Submit button", "confirm": "Confirm button", "add_card": "Add card button", "reserve_btn": "Reserve button",
                  "dish_card": "Dish card", "dish": "Dish button", "login": "Login button", "get_started": "Get started button"}
WIREFRAMES = {
    "txn_checkout": [[0, 0, 100, 11, "bar", "< Checkout"], [14, 6, 62, 3, "line"], [19, 6, 48, 3, "line"],
                     [30, 6, 88, 10, "box"], [48, 6, 88, 10, "box"], [66, 10, 80, 6, "line"], [85, 10, 80, 10, "btn", "Pay now"]],
}

COHORTS = [("shared", "Shared-device bursts", "crit"), ("otp", "Stalled at the OTP code", "warn"), ("big", "Big-deposit bookers", "accent"),
           ("load", "Rice-meal regulars", "accent"), ("price", "Menu browsers, sign up later", "info"),
           ("straight", "Straight-through completers", "accent"), ("other", "Other", "muted")]

VOCAB = {
    "conv_label": "Sign-up and login completion",
    "conv_sub": "{n} sign-up or login sessions that reach Signed up or Home",
    "funnel_start": "Started a sign-up, login, booking or order",
    "funnel_end": "Reached the success screen",
    "pat_amount_title": "{who} put down large deposits",
    "pat_amount_fact": "{share} of {who} booking deposits are above {cur} {thr:,} (median {cur} {med:,}), against {ref} for everyone else (median {cur} {refmed:,}).",
    "pat_prod_title": "{who} mostly order {prod}",
    "pat_prod_fact": "{share} of {who} orders are {prod}, against {ref} for everyone else.",
    "natural_assumption": "No value assumed: guests browsing the menu before signing up are not lost customers.",
    "intent_otp_raw": "OtpVerify view dwell_ms={dwell} frantic_press resend x{rage}",
    "intent_browse_raw": "MenuBrowse view press dish_card (guest)",
    "intent_browse": "Browsing the menu before signing up",
    "intent_pay_raw": "CheckoutPay category=group_platter frantic_press pay",
    "intent_risk_raw": "{last} fail (promo abuser, shared device)",
    "intent_unmapped_raw": "param sms_route_v2",
    "ask_burst_kw": ["otp", "code", "stall", "sign", "register", "login", "sms", "timestamp", "window", "resend", "dinner", "evening", "rush"],
    "ask_p4_q": "Which group drops off before an order is placed?",
    "ask_p4_kw": ["group", "order", "place", "placed", "family", "platter", "platters", "pay", "payment", "abandon", "drop", "checkout"],
    "ask_amount_q": "Who puts down large deposits?",
    "ask_amount_a": "{who} do: {share} of their booking deposits are above {cur} {thr:,} (median {cur} {med:,}). Everyone else has a median of {cur} {refmed:,}.",
    "ask_amount_kw": ["deposit", "deposits", "booking", "book", "large", "big", "office", "event", "php", "peso", "table"],
    "ask_prod_q": "What do Students order?",
    "ask_prod_a": "{share} of {who} orders are {prod}, against {ref} for other groups. This is expected behavior, not a problem.",
    "ask_prod_kw": ["student", "students", "order", "orders", "rice", "meal", "meals", "eat", "prefer"],
    "ask_risk_q": "Are promo abuser accounts a problem?",
    "ask_risk_a": "Promo abuser accounts fail far more often: {fact} {shared} devices are shared by 3 or more users. They are flagged as needing review, not classified.",
    "ask_risk_kw": ["promo", "abuse", "abuser", "abusers", "device", "shared", "burst", "failed", "attempts"],
    "ask_natural_q": "Why do guests leave at the menu?",
    "ask_natural_kw": ["guest", "guests", "menu", "natural", "exit", "browse", "sign"],
    "ask_control_kw": ["drop", "dropoff", "most", "where", "page", "pages", "reservation", "reserve", "booking", "table", "failed", "steady"],
    "sk_pay_q": "Show the journey of the diners who abandoned at checkout",
    "sk_pay_title": "Abandoned at checkout",
    "sk_pay_kw": ["journey", "abandon", "payment", "checkout", "pay", "order", "booking"],
    "sk_otp_q": "Where do people go after the OTP step fails?",
    "sk_otp_title": "Exited at OTP",
    "sk_otp_kw": ["otp", "fail", "resend", "phone", "verification"],
    "sk_group_q": "What happens to Students who leave before their order is placed?",
    "sk_group_title": "Students who left before their order was placed",
    "sk_group_persona": "Students",
    "sk_group_kw": ["student", "students", "order", "placed", "leave", "rice"],
}

PROFILE = {
    "id": "dining", "dataset": "synthetic-dining-v1",
    "SCREEN_LABELS": SCREEN_LABELS, "JOURNEY_LABELS": JOURNEY_LABELS, "PERSONA_LABELS": PERSONA_LABELS, "PRODUCT_LABELS": PRODUCT_LABELS,
    "UI_STEPS": UI_STEPS, "UI_JOURNEY_NAMES": UI_JOURNEY_NAMES, "VALUE_PER_SESSION": VALUE_PER_SESSION, "VALUE_ASSUMPTION": VALUE_ASSUMPTION,
    "ELEMENT_LABELS": ELEMENT_LABELS, "WIREFRAMES": WIREFRAMES, "COHORTS": COHORTS, "VOCAB": VOCAB, "JOURNEYS": JOURNEYS,
}
