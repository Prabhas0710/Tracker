"""Seed categories, default user, and soft merchant priors."""

from sqlalchemy.orm import Session

from app.models import (
    Category,
    MerchantPrior,
    Subcategory,
    User,
)

CATEGORY_TREE = {
    "Income": ["UPI Credit", "Bank Credit", "Refund", "Salary", "Other"],
    "Food": ["Food Delivery", "Restaurants", "Cafe", "Snacks"],
    "Groceries": ["Supermarket", "Kirana", "Other"],
    "Entertainment": ["Movies", "Streaming", "Events", "Games"],
    "Fuel": ["Petrol", "Diesel", "EV Charging"],
    "Transport": ["Taxi", "Ride Share", "Public Transit", "Vehicle Maintenance", "Parking"],
    "Shopping": ["Clothing", "Electronics", "General", "Online"],
    "Bills": ["Utilities", "Internet", "Mobile", "Rent"],
    "Recharge": ["Mobile", "DTH"],
    "Personal": ["General"],
    "Health": ["Pharmacy", "Clinic", "Insurance"],
    "Credit Card": ["Card Spend", "Bill Payment"],
    "Transfer": ["Self", "Account Transfer"],
    "Other": ["Miscellaneous", "Unknown"],
}

MERCHANT_PRIORS = [
    ("pvr", "PVR Cinemas", "Entertainment", "Movies", 0.98),
    ("pvr cinemas", "PVR Cinemas", "Entertainment", "Movies", 0.98),
    ("swiggy", "Swiggy", "Food", "Food Delivery", 0.99),
    ("zomato", "Zomato", "Food", "Food Delivery", 0.99),
    ("blinkit", "Blinkit", "Food", "Food Delivery", 0.99),
    ("zepto", "Zepto", "Food", "Food Delivery", 0.99),
    ("instamart", "Instamart", "Food", "Food Delivery", 0.99),
    ("dunzo", "Dunzo", "Food", "Food Delivery", 0.99),
    ("hpcl", "HPCL", "Fuel", "Petrol", 0.95),
    ("indian oil", "Indian Oil", "Fuel", "Petrol", 0.95),
    ("bpcl", "BPCL", "Fuel", "Petrol", 0.95),
    ("uber", "Uber", "Transport", "Taxi", 0.97),
    ("ola", "Ola", "Transport", "Taxi", 0.97),
    ("amazon", "Amazon", "Shopping", "Online", 0.90),
    ("flipkart", "Flipkart", "Shopping", "Online", 0.90),
    ("airtel", "Airtel", "Recharge", "Mobile", 0.95),
    ("airtel prepaid", "Airtel", "Recharge", "Mobile", 0.98),
    ("jio", "Jio", "Recharge", "Mobile", 0.95),
    ("jio prepaid", "Jio", "Recharge", "Mobile", 0.98),
]


def seed_database(db: Session) -> None:
    if not db.query(User).filter(User.id == 1).first():
        db.add(User(id=1, name="Prabhas", email="user@expense.local"))
        db.flush()

    for cat_name, subs in CATEGORY_TREE.items():
        category = db.query(Category).filter(Category.name == cat_name).first()
        if not category:
            category = Category(name=cat_name, description=f"{cat_name} expenses")
            db.add(category)
            db.flush()
        existing = {s.name for s in category.subcategories}
        for sub in subs:
            if sub not in existing:
                db.add(Subcategory(category_id=category.id, name=sub))

    for key, display, category, subcategory, confidence in MERCHANT_PRIORS:
        prior = db.query(MerchantPrior).filter(MerchantPrior.merchant_key == key).first()
        if prior:
            prior.merchant_display = display
            prior.category = category
            prior.subcategory = subcategory
            prior.confidence = confidence
        else:
            db.add(
                MerchantPrior(
                    merchant_key=key,
                    merchant_display=display,
                    category=category,
                    subcategory=subcategory,
                    confidence=confidence,
                )
            )
