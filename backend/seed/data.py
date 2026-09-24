"""Reference dataset for the MetriX demo corpus.

Everything here is synthetic but structurally faithful: real category taxonomy
from the Packaged Commodities Rules, plausible Indian brands, valid EAN-13 check
digits, and Delhi-NCR geography so the geofence and routing engine have real
polygons and coordinates to work against.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Categories -- slug, name, sector, icon, seasonal multiplier, rule pipeline
# The seasonal multiplier is what spec 3.C uses for festival risk weighting
# (sweets & ghee spike during Diwali).
# ---------------------------------------------------------------------------
BASE_RULES = [
    "mrp_format",
    "net_quantity",
    "unit_price",
    "manufacturer",
    "declarations",
    "multi_surface",
    "font_height",
]
FOOD_RULES = BASE_RULES + ["dates", "fssai"]

CATEGORIES: list[dict] = [
    # slug, name, sector, icon, seasonal, rules
    {"slug": "biscuits-cookies", "name": "Biscuits & Cookies", "sector": "Food", "icon": "cookie", "seasonal_multiplier": 1.3, "rule_pipeline": FOOD_RULES},
    {"slug": "edible-oils", "name": "Packaged Edible Oils", "sector": "Food", "icon": "droplet", "seasonal_multiplier": 1.8, "rule_pipeline": FOOD_RULES},
    {"slug": "dairy-products", "name": "Dairy Products", "sector": "Food", "icon": "milk", "seasonal_multiplier": 1.2, "rule_pipeline": FOOD_RULES},
    {"slug": "ghee-butter", "name": "Ghee & Butter", "sector": "Food", "icon": "butter", "seasonal_multiplier": 2.5, "rule_pipeline": FOOD_RULES},
    {"slug": "sweets-mithai", "name": "Packaged Sweets & Mithai", "sector": "Food", "icon": "candy", "seasonal_multiplier": 2.5, "rule_pipeline": FOOD_RULES},
    {"slug": "spices-masala", "name": "Local Spices & Masala", "sector": "Food", "icon": "pepper", "seasonal_multiplier": 1.6, "rule_pipeline": FOOD_RULES},
    {"slug": "atta-flour", "name": "Atta & Flour", "sector": "Food", "icon": "wheat", "seasonal_multiplier": 1.2, "rule_pipeline": FOOD_RULES},
    {"slug": "rice-grains", "name": "Rice & Grains", "sector": "Food", "icon": "rice", "seasonal_multiplier": 1.3, "rule_pipeline": FOOD_RULES},
    {"slug": "pulses-dal", "name": "Pulses & Dal", "sector": "Food", "icon": "beans", "seasonal_multiplier": 1.4, "rule_pipeline": FOOD_RULES},
    {"slug": "tea-coffee", "name": "Tea & Coffee", "sector": "Food", "icon": "coffee", "seasonal_multiplier": 1.1, "rule_pipeline": FOOD_RULES},
    {"slug": "snacks-namkeen", "name": "Snacks & Namkeen", "sector": "Food", "icon": "chips", "seasonal_multiplier": 1.5, "rule_pipeline": FOOD_RULES},
    {"slug": "chocolates-confectionery", "name": "Chocolates & Confectionery", "sector": "Food", "icon": "chocolate", "seasonal_multiplier": 1.9, "rule_pipeline": FOOD_RULES},
    {"slug": "beverages-juices", "name": "Beverages & Juices", "sector": "Food", "icon": "cup", "seasonal_multiplier": 1.4, "rule_pipeline": FOOD_RULES},
    {"slug": "instant-noodles", "name": "Instant Noodles & Pasta", "sector": "Food", "icon": "noodles", "seasonal_multiplier": 1.1, "rule_pipeline": FOOD_RULES},
    {"slug": "baby-food", "name": "Baby Food & Formula", "sector": "Food", "icon": "baby", "seasonal_multiplier": 1.0, "rule_pipeline": FOOD_RULES},
    {"slug": "breakfast-cereals", "name": "Breakfast Cereals", "sector": "Food", "icon": "bowl", "seasonal_multiplier": 1.0, "rule_pipeline": FOOD_RULES},
    {"slug": "sauces-condiments", "name": "Sauces & Condiments", "sector": "Food", "icon": "sauce", "seasonal_multiplier": 1.1, "rule_pipeline": FOOD_RULES},
    {"slug": "dry-fruits-nuts", "name": "Dry Fruits & Nuts", "sector": "Food", "icon": "nut", "seasonal_multiplier": 2.2, "rule_pipeline": FOOD_RULES},
    {"slug": "salt-sugar", "name": "Salt & Sugar", "sector": "Food", "icon": "salt", "seasonal_multiplier": 1.2, "rule_pipeline": FOOD_RULES},
    {"slug": "frozen-foods", "name": "Frozen & Ready to Eat", "sector": "Food", "icon": "snowflake", "seasonal_multiplier": 1.1, "rule_pipeline": FOOD_RULES},
    {"slug": "soaps-detergents", "name": "Soaps & Detergents", "sector": "FMCG", "icon": "soap", "seasonal_multiplier": 1.2, "rule_pipeline": BASE_RULES},
    {"slug": "personal-care", "name": "Personal Care", "sector": "FMCG", "icon": "lotion", "seasonal_multiplier": 1.1, "rule_pipeline": BASE_RULES},
    {"slug": "hair-care", "name": "Hair Care", "sector": "FMCG", "icon": "shampoo", "seasonal_multiplier": 1.0, "rule_pipeline": BASE_RULES},
    {"slug": "oral-care", "name": "Oral Care", "sector": "FMCG", "icon": "toothbrush", "seasonal_multiplier": 1.0, "rule_pipeline": BASE_RULES},
    {"slug": "cosmetics", "name": "Cosmetics & Beauty", "sector": "FMCG", "icon": "lipstick", "seasonal_multiplier": 1.7, "rule_pipeline": BASE_RULES},
    {"slug": "home-cleaning", "name": "Home Cleaning", "sector": "FMCG", "icon": "spray", "seasonal_multiplier": 1.3, "rule_pipeline": BASE_RULES},
    {"slug": "paper-hygiene", "name": "Paper & Hygiene", "sector": "FMCG", "icon": "tissue", "seasonal_multiplier": 1.0, "rule_pipeline": BASE_RULES},
    {"slug": "pharma-otc", "name": "OTC Health & Wellness", "sector": "Healthcare", "icon": "pill", "seasonal_multiplier": 1.0, "rule_pipeline": FOOD_RULES},
    {"slug": "electronics-small", "name": "Small Electronics", "sector": "Durables", "icon": "plug", "seasonal_multiplier": 1.9, "rule_pipeline": BASE_RULES},
    {"slug": "stationery", "name": "Stationery & Office", "sector": "Durables", "icon": "pen", "seasonal_multiplier": 1.0, "rule_pipeline": BASE_RULES},
]

# ---------------------------------------------------------------------------
# Products -- (category_slug, brand, product, mrp, qty_value, qty_unit, origin)
# ---------------------------------------------------------------------------
PRODUCTS: list[tuple] = [
    ("biscuits-cookies", "Parle Products", "Parle-G Original Glucose Biscuits", 10.00, 250, "g", "India"),
    ("biscuits-cookies", "Parle Products", "Parle Monaco Salted Biscuits", 30.00, 200, "g", "India"),
    ("biscuits-cookies", "Britannia Industries", "Britannia Good Day Cashew Cookies", 45.00, 200, "g", "India"),
    ("biscuits-cookies", "Britannia Industries", "Britannia Marie Gold", 35.00, 250, "g", "India"),
    ("biscuits-cookies", "Britannia Industries", "Britannia Bourbon Chocolate Cream", 40.00, 150, "g", "India"),
    ("biscuits-cookies", "ITC Limited", "Sunfeast Dark Fantasy Choco Fills", 80.00, 300, "g", "India"),
    ("biscuits-cookies", "ITC Limited", "Sunfeast Marie Light", 30.00, 250, "g", "India"),
    ("biscuits-cookies", "Anmol Industries", "Anmol Cream Treat Orange", 20.00, 120, "g", "India"),
    ("edible-oils", "Adani Wilmar", "Fortune Sunlite Refined Sunflower Oil", 145.00, 1, "L", "India"),
    ("edible-oils", "Adani Wilmar", "Fortune Kachi Ghani Mustard Oil", 175.00, 1, "L", "India"),
    ("edible-oils", "Marico", "Saffola Gold Blended Oil", 210.00, 1, "L", "India"),
    ("edible-oils", "Emami Agrotech", "Emami Healthy & Tasty Soyabean Oil", 135.00, 1, "L", "India"),
    ("edible-oils", "Cargill India", "Gemini Refined Sunflower Oil", 155.00, 1, "L", "India"),
    ("edible-oils", "Patanjali Ayurved", "Patanjali Kachi Ghani Mustard Oil", 180.00, 1, "L", "India"),
    ("dairy-products", "Mother Dairy", "Mother Dairy Full Cream Milk", 34.00, 500, "ml", "India"),
    ("dairy-products", "Amul (GCMMF)", "Amul Gold Full Cream Milk", 33.00, 500, "ml", "India"),
    ("dairy-products", "Amul (GCMMF)", "Amul Masti Dahi", 30.00, 400, "g", "India"),
    ("dairy-products", "Nestle India", "Nestle a+ Slim Milk", 36.00, 500, "ml", "India"),
    ("dairy-products", "Mother Dairy", "Mother Dairy Paneer", 95.00, 200, "g", "India"),
    ("ghee-butter", "Amul (GCMMF)", "Amul Pure Ghee", 640.00, 1, "L", "India"),
    ("ghee-butter", "Amul (GCMMF)", "Amul Butter Pasteurised", 56.00, 100, "g", "India"),
    ("ghee-butter", "Gowardhan (Parag Milk)", "Gowardhan Cow Ghee", 690.00, 1, "L", "India"),
    ("ghee-butter", "Patanjali Ayurved", "Patanjali Cow Desi Ghee", 610.00, 1, "L", "India"),
    ("ghee-butter", "Mother Dairy", "Mother Dairy Cow Ghee", 655.00, 1, "L", "India"),
    ("sweets-mithai", "Haldiram's", "Haldiram Soan Papdi", 155.00, 500, "g", "India"),
    ("sweets-mithai", "Haldiram's", "Haldiram Kaju Katli", 480.00, 400, "g", "India"),
    ("sweets-mithai", "Bikanervala", "Bikano Rasgulla Tin", 220.00, 1, "kg", "India"),
    ("sweets-mithai", "Bikanervala", "Bikano Gulab Jamun", 240.00, 1, "kg", "India"),
    ("spices-masala", "MDH", "MDH Deggi Mirch Powder", 85.00, 100, "g", "India"),
    ("spices-masala", "MDH", "MDH Chana Masala", 78.00, 100, "g", "India"),
    ("spices-masala", "Everest Spices", "Everest Garam Masala", 92.00, 100, "g", "India"),
    ("spices-masala", "Everest Spices", "Everest Turmeric Powder", 45.00, 200, "g", "India"),
    ("spices-masala", "Catch (DS Group)", "Catch Sprinklers Black Pepper", 110.00, 100, "g", "India"),
    ("spices-masala", "Aachi Masala", "Aachi Sambar Powder", 62.00, 200, "g", "India"),
    ("atta-flour", "ITC Limited", "Aashirvaad Shudh Chakki Atta", 245.00, 5, "kg", "India"),
    ("atta-flour", "Hindustan Unilever", "Annapurna Farm Fresh Atta", 235.00, 5, "kg", "India"),
    ("atta-flour", "Patanjali Ayurved", "Patanjali Whole Wheat Atta", 225.00, 5, "kg", "India"),
    ("rice-grains", "KRBL Limited", "India Gate Basmati Classic", 720.00, 5, "kg", "India"),
    ("rice-grains", "LT Foods", "Daawat Rozana Super Basmati", 480.00, 5, "kg", "India"),
    ("rice-grains", "Kohinoor Foods", "Kohinoor Authentic Basmati", 650.00, 5, "kg", "India"),
    ("pulses-dal", "Tata Consumer", "Tata Sampann Unpolished Toor Dal", 185.00, 1, "kg", "India"),
    ("pulses-dal", "Tata Consumer", "Tata Sampann Moong Dal", 165.00, 1, "kg", "India"),
    ("pulses-dal", "Organic Tattva", "Organic Tattva Chana Dal", 145.00, 500, "g", "India"),
    ("tea-coffee", "Tata Consumer", "Tata Tea Premium Leaf", 265.00, 500, "g", "India"),
    ("tea-coffee", "Hindustan Unilever", "Brooke Bond Red Label Tea", 255.00, 500, "g", "India"),
    ("tea-coffee", "Nestle India", "Nescafe Classic Instant Coffee", 340.00, 100, "g", "India"),
    ("tea-coffee", "Tata Consumer", "Tetley Green Tea Bags", 220.00, 50, "g", "India"),
    ("tea-coffee", "Wagh Bakri Tea", "Wagh Bakri Premium Tea", 260.00, 500, "g", "India"),
    ("snacks-namkeen", "Haldiram's", "Haldiram Aloo Bhujia", 55.00, 200, "g", "India"),
    ("snacks-namkeen", "Haldiram's", "Haldiram Navratan Mixture", 60.00, 200, "g", "India"),
    ("snacks-namkeen", "PepsiCo India", "Lay's India's Magic Masala", 20.00, 52, "g", "India"),
    ("snacks-namkeen", "PepsiCo India", "Kurkure Masala Munch", 20.00, 90, "g", "India"),
    ("snacks-namkeen", "Balaji Wafers", "Balaji Simply Salted Wafers", 20.00, 80, "g", "India"),
    ("snacks-namkeen", "Bikanervala", "Bikano Bhujia Sev", 52.00, 200, "g", "India"),
    ("chocolates-confectionery", "Mondelez India", "Cadbury Dairy Milk Silk", 90.00, 60, "g", "India"),
    ("chocolates-confectionery", "Mondelez India", "Cadbury 5 Star", 10.00, 22, "g", "India"),
    ("chocolates-confectionery", "Nestle India", "Nestle KitKat 4 Finger", 25.00, 27.5, "g", "India"),
    ("chocolates-confectionery", "Nestle India", "Nestle Munch Crunchy", 10.00, 18, "g", "India"),
    ("chocolates-confectionery", "Perfetti Van Melle", "Alpenliebe Gold Candy", 1.00, 3.5, "g", "India"),
    ("beverages-juices", "Dabur India", "Real Mixed Fruit Juice", 110.00, 1, "L", "India"),
    ("beverages-juices", "PepsiCo India", "Tropicana 100% Orange Juice", 125.00, 1, "L", "India"),
    ("beverages-juices", "Coca-Cola India", "Maaza Mango Drink", 65.00, 1.2, "L", "India"),
    ("beverages-juices", "Parle Agro", "Frooti Mango Drink", 20.00, 150, "ml", "India"),
    ("beverages-juices", "Bisleri International", "Bisleri Packaged Drinking Water", 20.00, 1, "L", "India"),
    ("instant-noodles", "Nestle India", "Maggi 2-Minute Masala Noodles", 14.00, 70, "g", "India"),
    ("instant-noodles", "ITC Limited", "Sunfeast YiPPee! Magic Masala", 15.00, 70, "g", "India"),
    ("instant-noodles", "Nissin Foods India", "Top Ramen Curry Noodles", 14.00, 70, "g", "India"),
    ("instant-noodles", "CG Foods", "Wai Wai Quick Noodles", 15.00, 75, "g", "India"),
    ("baby-food", "Nestle India", "Cerelac Wheat Baby Cereal", 285.00, 300, "g", "India"),
    ("baby-food", "Nestle India", "Nan Pro 1 Infant Formula", 720.00, 400, "g", "India"),
    ("baby-food", "Danone India", "Aptamil Stage 1 Formula", 780.00, 400, "g", "India"),
    ("breakfast-cereals", "Kellogg India", "Kellogg's Corn Flakes Original", 240.00, 475, "g", "India"),
    ("breakfast-cereals", "Kellogg India", "Kellogg's Chocos", 210.00, 375, "g", "India"),
    ("breakfast-cereals", "Bagrry's India", "Bagrry's White Oats", 195.00, 1, "kg", "India"),
    ("sauces-condiments", "Nestle India", "Maggi Rich Tomato Ketchup", 110.00, 900, "g", "India"),
    ("sauces-condiments", "Kissan (HUL)", "Kissan Fresh Tomato Ketchup", 105.00, 850, "g", "India"),
    ("sauces-condiments", "Veeba Foods", "Veeba Chinese Schezwan Chutney", 99.00, 320, "g", "India"),
    ("sauces-condiments", "Mother's Recipe", "Mother's Recipe Mango Pickle", 135.00, 500, "g", "India"),
    ("dry-fruits-nuts", "Nutraj", "Nutraj California Almonds", 640.00, 500, "g", "USA"),
    ("dry-fruits-nuts", "Happilo", "Happilo Premium Cashews W240", 720.00, 500, "g", "India"),
    ("dry-fruits-nuts", "Vedaka (Amazon)", "Vedaka Popular Raisins", 210.00, 500, "g", "India"),
    ("dry-fruits-nuts", "Nutraj", "Nutraj Iranian Pistachios", 890.00, 500, "g", "Iran"),
    ("salt-sugar", "Tata Consumer", "Tata Salt Iodised", 28.00, 1, "kg", "India"),
    ("salt-sugar", "Hindustan Unilever", "Annapurna Iodised Salt", 26.00, 1, "kg", "India"),
    ("salt-sugar", "Dhampur Sugar", "Dhampure Refined Sugar", 52.00, 1, "kg", "India"),
    ("frozen-foods", "McCain Foods India", "McCain French Fries", 155.00, 750, "g", "India"),
    ("frozen-foods", "ITC Limited", "ITC Master Chef Chicken Nuggets", 260.00, 500, "g", "India"),
    ("frozen-foods", "Godrej Tyson Foods", "Yummiez Veg Spring Roll", 185.00, 400, "g", "India"),
    ("soaps-detergents", "Hindustan Unilever", "Surf Excel Easy Wash Powder", 220.00, 2, "kg", "India"),
    ("soaps-detergents", "Procter & Gamble", "Ariel Matic Front Load", 340.00, 2, "kg", "India"),
    ("soaps-detergents", "Rohit Surfactants", "Ghadi Detergent Powder", 145.00, 2, "kg", "India"),
    ("soaps-detergents", "Hindustan Unilever", "Lifebuoy Total 10 Soap", 42.00, 125, "g", "India"),
    ("soaps-detergents", "Wipro Consumer", "Santoor Sandal Soap", 40.00, 125, "g", "India"),
    ("soaps-detergents", "Godrej Consumer", "Godrej No.1 Sandal Soap", 38.00, 100, "g", "India"),
    ("personal-care", "Hindustan Unilever", "Vaseline Intensive Care Lotion", 275.00, 400, "ml", "India"),
    ("personal-care", "Nivea India", "Nivea Soft Light Moisturiser", 299.00, 300, "ml", "India"),
    ("personal-care", "Emami Limited", "Boroplus Antiseptic Cream", 95.00, 120, "ml", "India"),
    ("personal-care", "Himalaya Wellness", "Himalaya Purifying Neem Face Wash", 180.00, 150, "ml", "India"),
    ("hair-care", "Hindustan Unilever", "Clinic Plus Strong & Long Shampoo", 199.00, 355, "ml", "India"),
    ("hair-care", "Marico", "Parachute Advansed Coconut Hair Oil", 165.00, 400, "ml", "India"),
    ("hair-care", "Dabur India", "Dabur Amla Hair Oil", 145.00, 450, "ml", "India"),
    ("hair-care", "Bajaj Consumer", "Bajaj Almond Drops Hair Oil", 175.00, 300, "ml", "India"),
    ("oral-care", "Colgate-Palmolive", "Colgate Strong Teeth Toothpaste", 105.00, 200, "g", "India"),
    ("oral-care", "Dabur India", "Dabur Red Paste", 98.00, 200, "g", "India"),
    ("oral-care", "Patanjali Ayurved", "Patanjali Dant Kanti Toothpaste", 90.00, 200, "g", "India"),
    ("cosmetics", "Lakme (HUL)", "Lakme Absolute Matte Lipstick", 725.00, 3.7, "g", "India"),
    ("cosmetics", "Maybelline India", "Maybelline Fit Me Foundation", 549.00, 30, "ml", "USA"),
    ("cosmetics", "Nykaa E-Retail", "Nykaa So Matte Lipstick", 399.00, 4.2, "g", "India"),
    ("home-cleaning", "Reckitt Benckiser", "Harpic Power Plus Toilet Cleaner", 195.00, 1, "L", "India"),
    ("home-cleaning", "Reckitt Benckiser", "Lizol Disinfectant Floor Cleaner", 215.00, 975, "ml", "India"),
    ("home-cleaning", "Hindustan Unilever", "Vim Dishwash Liquid Gel", 175.00, 750, "ml", "India"),
    ("paper-hygiene", "Procter & Gamble", "Whisper Ultra Clean XL Wings", 299.00, 30, "N", "India"),
    ("paper-hygiene", "Origami Cellulo", "Origami Kitchen Towel Roll", 189.00, 4, "N", "India"),
    ("paper-hygiene", "Unicharm India", "MamyPoko Pants Extra Absorb L", 799.00, 46, "N", "India"),
    ("pharma-otc", "Dabur India", "Dabur Chyawanprash Awaleha", 385.00, 1, "kg", "India"),
    ("pharma-otc", "Himalaya Wellness", "Himalaya Liv.52 Tablets", 155.00, 100, "N", "India"),
    ("pharma-otc", "Zandu (Emami)", "Zandu Balm Pain Relief", 65.00, 25, "ml", "India"),
    ("pharma-otc", "Abbott India", "Digene Antacid Gel Mint", 145.00, 200, "ml", "India"),
    ("electronics-small", "Eveready Industries", "Eveready Ultima AA Alkaline 4N", 130.00, 4, "N", "India"),
    ("electronics-small", "Duracell India", "Duracell Plus AAA Batteries 4N", 165.00, 4, "N", "China"),
    ("electronics-small", "Philips India", "Philips 9W LED Bulb Cool Day", 145.00, 1, "N", "India"),
    ("electronics-small", "Syska LED", "Syska 12W LED Bulb", 175.00, 1, "N", "India"),
    ("stationery", "ITC Limited", "Classmate Notebook Single Line", 60.00, 172, "N", "India"),
    ("stationery", "Linc Pen & Plastics", "Linc Ocean Gel Pen Pack", 50.00, 5, "N", "India"),
    ("stationery", "Hindustan Pencils", "Apsara Platinum Extra Dark Pencils", 45.00, 10, "N", "India"),
    ("stationery", "Faber-Castell India", "Faber-Castell Wax Crayons", 95.00, 24, "N", "India"),
]

# ---------------------------------------------------------------------------
# Delhi-NCR retail geography for routing, geofencing and the radar
# ---------------------------------------------------------------------------
STORES: list[dict] = [
    {"name": "Sharma Supermart", "address": "12/4 Karol Bagh Main Road, New Delhi 110005", "lat": 28.6519, "lng": 77.1909, "type": "SUPERMARKET"},
    {"name": "City Wholesale Depot", "address": "Naya Bazar, Chandni Chowk, Delhi 110006", "lat": 28.6562, "lng": 77.2214, "type": "WHOLESALE"},
    {"name": "Gupta General Store", "address": "B-14 Lajpat Nagar II, New Delhi 110024", "lat": 28.5677, "lng": 77.2433, "type": "KIRANA"},
    {"name": "Verma Kirana Bhandar", "address": "Shop 8, Sarojini Nagar Market, New Delhi 110023", "lat": 28.5772, "lng": 77.1956, "type": "KIRANA"},
    {"name": "Apna Bazaar Retail", "address": "Sector 18, Noida, Uttar Pradesh 201301", "lat": 28.5708, "lng": 77.3260, "type": "SUPERMARKET"},
    {"name": "Modern Provision Store", "address": "Green Park Extension, New Delhi 110016", "lat": 28.5583, "lng": 77.2065, "type": "KIRANA"},
    {"name": "Balaji Trading Company", "address": "Khari Baoli Spice Market, Delhi 110006", "lat": 28.6570, "lng": 77.2181, "type": "WHOLESALE"},
    {"name": "Fresh Mart Hypermarket", "address": "Rajouri Garden, New Delhi 110027", "lat": 28.6469, "lng": 77.1200, "type": "HYPERMARKET"},
    {"name": "Singh Departmental Store", "address": "Model Town Phase 2, Delhi 110009", "lat": 28.7089, "lng": 77.1934, "type": "SUPERMARKET"},
    {"name": "Annapurna Grocers", "address": "Dwarka Sector 12, New Delhi 110078", "lat": 28.5921, "lng": 77.0460, "type": "KIRANA"},
    {"name": "Metro Cash Carry Depot", "address": "Netaji Subhash Place, Pitampura, Delhi 110034", "lat": 28.6942, "lng": 77.1520, "type": "WHOLESALE"},
    {"name": "Jain Sweets & Provisions", "address": "Kamla Nagar Market, Delhi 110007", "lat": 28.6812, "lng": 77.2064, "type": "KIRANA"},
    {"name": "Gurgaon Value Store", "address": "Sector 14 Market, Gurugram, Haryana 122001", "lat": 28.4692, "lng": 77.0322, "type": "SUPERMARKET"},
    {"name": "Krishna Provision Mart", "address": "Mayur Vihar Phase 1, Delhi 110091", "lat": 28.6042, "lng": 77.2903, "type": "KIRANA"},
    {"name": "Om Traders Wholesale", "address": "Azadpur Mandi Road, Delhi 110033", "lat": 28.7075, "lng": 77.1750, "type": "WHOLESALE"},
    {"name": "Daily Needs Superstore", "address": "Vasant Kunj B Block, New Delhi 110070", "lat": 28.5200, "lng": 77.1591, "type": "SUPERMARKET"},
    {"name": "Agarwal Kirana Store", "address": "Shahdara Main Market, Delhi 110032", "lat": 28.6733, "lng": 77.2894, "type": "KIRANA"},
    {"name": "Star Bazaar Retail", "address": "Janakpuri District Centre, New Delhi 110058", "lat": 28.6219, "lng": 77.0878, "type": "HYPERMARKET"},
]

# Officer jurisdiction polygons (simplified bounding boxes over real Delhi zones)
JURISDICTIONS: dict[str, dict] = {
    "Delhi Central Zone": {
        "type": "Polygon",
        "coordinates": [[[77.1500, 28.6100], [77.2600, 28.6100], [77.2600, 28.7000], [77.1500, 28.7000], [77.1500, 28.6100]]],
    },
    "Delhi South Zone": {
        "type": "Polygon",
        "coordinates": [[[77.1400, 28.5000], [77.3000, 28.5000], [77.3000, 28.6100], [77.1400, 28.6100], [77.1400, 28.5000]]],
    },
    "Delhi West Zone": {
        "type": "Polygon",
        "coordinates": [[[77.0300, 28.5800], [77.1500, 28.5800], [77.1500, 28.7000], [77.0300, 28.7000], [77.0300, 28.5800]]],
    },
    "Delhi North Zone": {
        "type": "Polygon",
        "coordinates": [[[77.1300, 28.6800], [77.3000, 28.6800], [77.3000, 28.7600], [77.1300, 28.7600], [77.1300, 28.6800]]],
    },
    "Gautam Buddh Nagar (Noida)": {
        "type": "Polygon",
        "coordinates": [[[77.2900, 28.4800], [77.4500, 28.4800], [77.4500, 28.6200], [77.2900, 28.6200], [77.2900, 28.4800]]],
    },
}

# ---------------------------------------------------------------------------
# Rule catalogue -- used for the policy dashboard's "most violated clauses"
# ---------------------------------------------------------------------------
LEGAL_CLAUSES: dict[str, str] = {
    "mrp_format": "Rule 6(1)(e) - Retail Sale Price Declaration",
    "mrp_inclusive": "Rule 2(m) - MRP Inclusive of All Taxes",
    "net_quantity": "Rule 6(1)(d) - Net Quantity Declaration",
    "net_quantity_units": "Rule 8 - Metric Units of Measurement",
    "unit_price": "Rule 6(2) - Unit Sale Price Declaration",
    "mfg_date": "Rule 6(1)(c) - Month & Year of Manufacture",
    "expiry_date": "Rule 6(1)(c) - Best Before / Use By Date",
    "expired_stock": "Section 36 LM Act 2009 - Sale of Expired Commodity",
    "manufacturer": "Rule 6(1)(a) - Name & Address of Manufacturer",
    "pincode": "Rule 6(1)(a) - Complete Address with PIN Code",
    "country_of_origin": "Rule 6(1)(f) - Country of Origin Declaration",
    "customer_care": "Rule 6(1)(g) - Consumer Care Contact Details",
    "fssai_licence": "FSS (Packaging & Labelling) Regulations 2011",
    "font_height": "Rule 11 - Minimum Height of Numerals & Letters",
    "multi_surface": "Rule 9 - Principal Display Panel Requirements",
    "ecom_declaration": "Rule 6(10) - Mandatory E-Commerce Declarations",
}

# Statutory penalty bands (Legal Metrology Act 2009, Sections 25-36)
PENALTY_BANDS: dict[str, float] = {
    "mrp_format": 25_000.0,
    "mrp_inclusive": 25_000.0,
    "net_quantity": 25_000.0,
    "net_quantity_units": 10_000.0,
    "unit_price": 10_000.0,
    "mfg_date": 25_000.0,
    "expiry_date": 50_000.0,
    "expired_stock": 100_000.0,
    "manufacturer": 25_000.0,
    "pincode": 10_000.0,
    "country_of_origin": 25_000.0,
    "customer_care": 10_000.0,
    "fssai_licence": 50_000.0,
    "font_height": 10_000.0,
    "multi_surface": 25_000.0,
    "ecom_declaration": 50_000.0,
}


def ean13_check_digit(first12: str) -> str:
    """Standard GS1 modulo-10 check digit."""
    total = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(first12))
    return str((10 - total % 10) % 10)


def make_ean13(seq: int) -> str:
    """Deterministic valid EAN-13 in the Indian '890' GS1 prefix range."""
    body = f"890{seq:09d}"[:12]
    return body + ean13_check_digit(body)
