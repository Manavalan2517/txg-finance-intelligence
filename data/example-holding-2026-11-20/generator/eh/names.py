"""Made-up names for people, customers and suppliers.

Every name here is invented for Example Holding. Government and semi-government bodies use numbered regions
or invented places so they cannot be read as real institutions. The class of each counterparty (government,
private, related party...) is never written into the Zoho files; it goes to the answer key only.
"""

SA_FIRST = ["Mohammed", "Abdullah", "Fahad", "Faisal", "Khalid", "Sultan", "Turki", "Nasser", "Saud", "Omar",
            "Yousef", "Majed", "Bandar", "Saleh", "Ibrahim", "Abdulaziz", "Noura", "Sara", "Reem", "Lama", "Hessa",
            "Maha", "Abeer", "Hind", "Rakan", "Ziyad", "Mishal", "Haifa"]
SA_LAST = ["Al-Harbi", "Al-Qahtani", "Al-Otaibi", "Al-Shehri", "Al-Ghamdi", "Al-Zahrani", "Al-Dosari", "Al-Mutairi",
           "Al-Anazi", "Al-Shammari", "Al-Subaie", "Al-Malki", "Al-Juhani", "Al-Rashidi", "Al-Omari", "Al-Yami"]
EXPATS = ["Rajesh Menon", "Imran Qureshi", "Ahmed Fathy", "Mohamed Sami", "Joseph Mathew", "Maria Santos",
          "Arun Kumar", "Bilal Siddiqui", "Hany Mansour", "Tariq Mahmood", "Sunil Nair", "Ramy Saad", "Vinod Pillai",
          "Kamal Haddad", "Grace Dela Cruz", "Osama Khalil"]

# ---------------------------------------------------------------- contracting
CON_GOV = ["Municipality of Wadi Sahab", "Directorate of Public Works – Region 7", "Regional Health Cluster 9",
           "Water Authority – Southern Sector 4", "Education Facilities Directorate – Region 3",
           "Roads and Transport Directorate – Region 5", "Municipality of Ras Tamra", "Housing Projects Agency – Region 2",
           "Directorate of Public Works – Region 11", "Regional Health Cluster 6", "Municipality of Jabal Noor",
           "Sports Facilities Agency – Region 8", "Water Authority – Northern Sector 2", "Airports Works Directorate – Region 1"]
CON_SEMI = ["Al-Ufuq Development Company", "Northern Gateway Development Co.", "Coastal Leisure Development Co.",
            "Rawdat Housing Development Co.", "Industrial Cities Services Co. – Zone 4", "Heritage Districts Development Co."]
CON_PRIVATE = ["Stonebridge Real Estate Development", "Palmgate Malls Company", "Falconridge Industrial Park Co.",
               "Sandcrest Residential Developers", "Bluedune Hospitality Projects", "Cedarline Office Parks",
               "Greenoasis Schools Company", "Highdune Logistics Parks", "Silverpalm Medical Centres",
               "Amberline Hotels Development", "Northstar Towers Co.", "Brightway Retail Parks", "Oakfield Compounds Co."]
CON_VENDORS = {
    "materials": ["Ironwood Steel Trading", "Sunvale Readymix Concrete", "Clearwater Pipes and Fittings",
                  "Goldleaf Cement Distributors", "Redstone Blocks Factory", "Swiftline Electrical Supplies",
                  "Crescent Bay Aluminium and Glass", "Highline Insulation Materials", "Duneview Paints Trading",
                  "Palmcrest Timber and Formwork", "Tamarisk Building Supplies", "Safa Rebar Trading"],
    "subcontract": ["Northgate MEP Contracting", "Al-Sanad Earthworks Co.", "Brightline Façade Systems",
                    "Coralstone Finishing Works", "Sandhill Piling and Foundations", "Desert Arc HVAC Contracting",
                    "Bluewave Waterproofing Co.", "Falcon Steel Erection Co.", "Greenleaf Landscaping Contractors",
                    "Ridgeway Electrical Contracting"],
    "plant": ["Summit Equipment Rental", "Heavylift Cranes Hire", "Rimstone Plant and Machinery Hire",
              "Oasis Scaffolding Services"],
}

# ---------------------------------------------------------------- food distribution
TRD_KEY = ["Oasis Fresh Hypermarkets", "Basket Plus Supermarkets", "DailyMart Stores", "Al-Khair Markets",
           "Green Valley Supermarkets", "Family Choice Hypermarket", "Sunrise Mini Marts", "City Basket Stores",
           "Golden Cart Hypermarkets", "Value Corner Markets"]
TRD_HORECA_A = ["Palm", "Sahara", "Najd Gardens", "Bayside", "Saffron", "Cedar", "Olive Tree", "Golden Spoon",
                "Silver Fork", "Desert Rose", "Al-Diwan", "Coastline", "Garden View", "Lantern", "Spice Route",
                "Majlis", "Harbour", "Crescent", "Tamr", "Qahwa House", "Al-Bustan", "Rawabi", "Sidra", "Zaytoon",
                "Marina", "Sanabel", "Falcon", "Hilltop", "Riverside", "Sunset"]
TRD_HORECA_B = ["Café", "Restaurants", "Grill", "Kitchen", "Bistro", "Catering Co.", "Hotel", "Bakery", "Diner",
                "Shawarma", "Coffee Roasters", "Pastry House", "Burger Co.", "Mandi House", "Seafood"]
TRD_WHOLESALE = ["Al-Amal Wholesale Foods", "Barakah Food Traders", "Najm Distribution Est.", "Al-Rayyan Foodstuff Trading",
                 "Mawared Wholesale Co.", "Al-Wafa Provisions", "Thimar Foodstuff Est.", "Tayba Wholesale Trading",
                 "Hasad Food Supplies", "Rukn Al-Sahra Trading", "Al-Nakheel Provisions", "Saqr Foodstuff Trading",
                 "Bawadi Wholesale", "Al-Tayyib Food Est.", "Manar Wholesale Foods", "Al-Sufra Trading"]
TRD_GOV = ["Regional Health Cluster 3 – Patient Catering", "Education Directorate – School Canteens Region 2",
           "Directorate of Social Services – Region 6 Care Homes", "Regional Health Cluster 8 – Patient Catering"]
TRD_SMALL_A = ["Baqala", "Mini Market", "Grocery", "Corner Shop", "Tamweenat", "Food Store"]
TRD_SMALL_B = ["Al-Noor", "Al-Salam", "Al-Huda", "Al-Fajr", "Al-Rahma", "Al-Iman", "Al-Majd", "Al-Bayan", "Al-Afrah",
               "Al-Shifa", "Al-Saada", "Al-Khaleej", "Al-Jazeera", "Al-Wadi", "Al-Sahel", "Al-Qamar", "Al-Shams",
               "Al-Hilal", "Al-Nasr", "Al-Yasmeen", "Al-Reef", "Al-Madina", "Al-Salama", "Al-Hamra"]
TRD_VENDORS_SAR = ["Golden Grain Mills", "Desert Dairy Co.", "Sahel Cooking Oils Factory", "Najd Juices Co.",
                   "Tihama Canning Co.", "Sweet Dune Confectionery", "Al-Kharj Poultry Farms", "Red Sea Salt and Spices",
                   "Hijaz Bottled Water Co.", "Qassim Dates Packing Co.", "Eastern Flour and Sugar Co.",
                   "Asir Coffee Roasters", "Jazan Pasta Factory", "Tabuk Frozen Foods Co."]
TRD_VENDORS_EUR = ["Nordhof Dairy GmbH", "Casa Verde Alimentari S.r.l.", "Dutch Meadow Foods B.V.",
                   "Belle Prairie Fromages SAS", "Olivar del Sur S.L.", "Alpenhaus Confiserie AG"]
TRD_VENDORS_USD = ["Pacific Rice Exporters Pvt Ltd", "Siam Golden Rice Co.", "Brasa Poultry Exports Ltda",
                   "Ceylon Highlands Tea Co.", "Prairie Valley Foods Inc."]
TRD_CLEARING = "Gulf Gate Customs Clearing Est."

# ---------------------------------------------------------------- retail (home and lifestyle)
RET_MALLS = [("Palmgate Mall", "Riyadh"), ("Sunvale Centre", "Riyadh"), ("Crescent Walk", "Jeddah"),
             ("Bayside Mall", "Jeddah"), ("Najd Galleria", "Riyadh"), ("Corniche Plaza", "Dammam"),
             ("Oasis Avenue", "Khobar"), ("Rawabi Park Mall", "Riyadh"), ("Hijaz Square", "Makkah"),
             ("Garden City Mall", "Madinah"), ("Falcon Point", "Riyadh"), ("Marina Walk", "Jeddah"),
             ("Desert Pearl Mall", "Qassim"), ("Highland Centre", "Abha"), ("Eastgate Mall", "Dammam"),
             ("Tamr Plaza", "Al-Ahsa"), ("Silverline Mall", "Riyadh"), ("Harbour Point", "Jeddah"),
             ("Cedar Mall", "Taif"), ("Northern Lights Mall", "Tabuk"), ("Sidra Centre", "Riyadh"),
             ("Al-Bustan Mall", "Khobar"), ("Majlis Mall", "Riyadh"), ("Lantern Walk", "Jeddah"),
             ("Seaview Mall", "Yanbu"), ("Golden Sands Mall", "Hail"), ("Al-Waha Mall", "Riyadh"),
             ("Kingsway Centre", "Riyadh"), ("Sunset Boulevard Mall", "Jeddah"), ("Spice Route Mall", "Jazan"),
             ("Oakfield Mall", "Riyadh"), ("Rimal Centre", "Dammam"), ("Hilltop Mall", "Taif"),
             ("Riverside Mall", "Riyadh"), ("Zaytoon Mall", "Jeddah"), ("Qahwa Square", "Buraidah"),
             ("Sanabel Mall", "Riyadh"), ("Coastline Mall", "Jubail"), ("Al-Diwan Centre", "Khamis Mushait"),
             ("Bluedune Mall", "Riyadh"), ("Al-Rayyan Mall", "Riyadh"), ("Pearl Gate Mall", "Jeddah"),
             ("Sahara Walk", "Dammam"), ("Juniper Mall", "Riyadh"), ("Summit Plaza", "Abha"), ("Palm Bay Centre", "Khobar")]
RET_LANDLORDS = ["Palmgate Malls Company", "Sunvale Centres Co.", "Crescent Retail Properties", "Bayside Leisure Co.",
                 "Najd Real Estate Investment Co.", "Eastern Malls Development Co.", "Hijaz Retail Estates",
                 "Rawabi Property Management", "Northstar Malls Co.", "Cedarline Retail Real Estate"]
RET_VENDORS = {
    "SAR": ["Al-Fakhama Home Supplies", "Najd Furnishing Trading", "Desert Rose Textiles Est.",
            "Saudi Glassware Distributors", "Comfort Line Bedding Factory"],
    "CNY": ["Ningbo Harbour Homeware Co.", "Foshan Bright Ceramics Co.", "Yiwu Crafts Trading Co."],
    "EUR": ["Lumière Décor SARL", "Porto Linho Têxteis Lda."],
    "USD": ["Anatolia Home Textiles Ltd", "Moradabad Brassware Exports"],
}
RET_FITOUT = "Brightline Interiors Fit-out Co."

# ---------------------------------------------------------------- common overhead suppliers
OVERHEAD = {
    "utilities": "Example Electricity Distribution Co.",
    "water": "Example Water Services Co.",
    "telecom": "Example Telecom Business Services",
    "it": "Cloudline Software Subscriptions",
    "audit": "Example Audit and Advisory (Chartered Accountants)",
    "legal": "Example Law Firm",
    "insurance": "Example Cooperative Insurance Co.",
    "security": "Shield Security Services Co.",
    "cleaning": "Sparkle Facility Cleaning Co.",
    "travel": "Skyway Travel and Tourism",
    "marketing": "Brightspark Advertising Agency",
    "printing": "Quickprint Stationery and Printing",
    "maintenance": "Fixwell Maintenance Services",
    "fleet": "Roadrunner Fuel and Fleet Services",
    "office_landlord": "Cedarline Office Parks",
    "warehouse_landlord": "Highdune Logistics Parks",
    "equipment": "Summit Machinery Trading",
    "vehicles": "Example Motors Fleet Sales",
    "camp": "Desert Camp Accommodation Services",
    "fleet_rental": "Swift Fleet Rental Co.",
    "racking": "Highbay Warehouse Systems Co.",
    "it_hardware": "Bytewise Computer Systems",
}

# ---------------------------------------------------------------- building materials and industrial supplies
BM_VENDORS = {
    "SAR": ["Sahara Cement Works", "Rimstone Blocks Factory", "Ironcrest Rebar Mills", "Palmline Pipes Industries",
            "Coloursand Paints Factory", "Brightwire Cables Co."],
    "USD": ["Meridian Steel Exports Ltd", "Anatolian Rebar Exports Ltd"],
    "EUR": ["Cerámica Solana S.L.", "Ponte Sanitari S.p.A.", "Farbwerk Chemie GmbH"],
    "CNY": ["Foshan Tilecraft Co.", "Ningbo Fluidline Valves Co.", "Wenzhou Brightswitch Electric Co."],
}
IND_VENDORS = {
    "SAR": ["Petroline Lubricants Blending Co.", "Steelgrip Fasteners Factory", "Guardwell Safety Supplies"],
    "USD": ["Atlas Pump Systems Inc.", "Lubritech Industrial LLC"],
    "EUR": ["Kugelwerk Lager GmbH", "Valvola Tecnica S.r.l."],
    "CNY": ["Shenzhen Safeguard PPE Co.", "Hangzhou Toolmaster Co.", "Zhejiang Flowcontrol Valves Co."],
}
CUST_WORDS = ["Al-Noor", "Al-Salam", "Al-Huda", "Al-Fajr", "Al-Majd", "Al-Bayan", "Al-Khaleej", "Al-Wadi", "Al-Sahel",
              "Al-Qamar", "Al-Shams", "Al-Hilal", "Al-Nasr", "Al-Reef", "Al-Madina", "Al-Hamra", "Rawabi", "Sidra",
              "Tamr", "Bayside", "Cedar", "Crescent", "Falcon", "Garden", "Harbour", "Lantern", "Marina", "Oasis",
              "Palm", "Sanabel", "Summit", "Sunrise", "Zaytoon", "Desert Rose", "Golden Sand", "Silver Dune"]
BM_GOV = ["Housing Projects Agency – Region 4 Stores", "Directorate of Public Works – Region 2 Stores",
          "Municipality of Ras Tamra – Maintenance Stores", "Education Facilities Directorate – Region 6 Stores"]
IND_GOV = ["Water Authority – Southern Sector 4 Workshops", "Regional Health Cluster 9 – Engineering Stores",
           "Roads and Transport Directorate – Region 5 Depots"]
IND_BIG = "Eastline Petrochemical Services Co."

# ---------------------------------------------------------------- facility management
FM_VENDORS = {
    "materials": ["Quickfix Maintenance Supplies", "Sparkline Cleaning Chemicals", "Coolair HVAC Spares Trading",
                  "Brightlamp Electrical Spares", "Aquaflow Plumbing Spares", "Uniformline Workwear Est."],
    "subcontract": ["Liftcare Elevator Services", "Pestguard Environmental Services", "Greenleaf Landscaping Contractors",
                    "Wastewise Collection Co.", "Firesafe Systems Maintenance"],
    "plant": ["Swift Fleet Rental Co.", "Highreach Access Equipment Hire", "Scrubtech Equipment Rental"],
}
