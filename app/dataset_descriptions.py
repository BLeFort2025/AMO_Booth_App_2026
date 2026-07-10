"""
Plain-English dataset descriptions for non-expert users.

Each entry maps a StatCan / OMAFRA table-ID to a short sentence
explaining *what* the data measures and *why* it matters.
Shown as an info block above the chart.
"""

DATASET_DESCRIPTIONS: dict[str, str] = {

    # ── Farm finance core ─────────────────────────────────────────────
    "32-10-0045-01": (
        "Tracks how much money Canadian farms earn from selling crops, "
        "livestock, and other products — the total cash flowing into "
        "farms before expenses are deducted."
    ),
    "32-10-0049-01": (
        "Shows what farms spend to operate each year — from feed and "
        "fertilizer to fuel, labour, and equipment depreciation."
    ),
    "32-10-0050-01": (
        "Measures the total value of farm assets: land, buildings, "
        "equipment, and livestock. Rising values signal greater "
        "investment in the sector."
    ),
    "32-10-0051-01": (
        "Tracks total farm debt owed to banks, government agencies, "
        "and other lenders. Helps gauge the financial leverage of "
        "the farming sector."
    ),
    "32-10-0052-01": (
        "Breaks net farm income into its components — market revenues, "
        "program payments, expenses, and depreciation — to show where "
        "farm profits come from."
    ),
    "32-10-0056-01": (
        "A snapshot of everything Canadian agriculture owns versus "
        "what it owes — the sector's balance sheet, showing assets, "
        "liabilities, and net worth."
    ),
    "32-10-0136-01": (
        "Revenue and expense estimates for farms — similar to a "
        "profit-and-loss statement showing whether the sector is "
        "earning more than it spends."
    ),
    "32-10-0047-01": (
        "Measures the value of agricultural production consumed on-farm, "
        "such as feed grown and used by the same operation — income "
        "that doesn't appear in cash receipts."
    ),
    "32-10-0046-01": (
        "Tracks direct government payments to farmers — crop insurance, "
        "stabilization programs, and disaster relief — showing how much "
        "support flows to the sector."
    ),
    "32-10-0078-01": (
        "Financial performance of farms grouped by type (dairy, grain, "
        "livestock, etc.) — showing how profitability varies across "
        "different kinds of farming."
    ),

    # ── Balance sheet & financial structure detail ─────────────────────
    "32-10-0101-01": (
        "Detailed financial statistics from farm tax records — revenue, "
        "expenses, assets, and liabilities — providing a comprehensive "
        "financial picture."
    ),
    "32-10-0102-01": (
        "Average financial structure per farm, broken down by farm type. "
        "Shows how revenue, debt, and assets differ between, say, a "
        "dairy farm and a grain operation."
    ),
    "32-10-0103-01": (
        "Average financial structure per farm, grouped by revenue class. "
        "Reveals how the economics change as farms grow larger."
    ),
    "32-10-0104-01": (
        "Tracks what farms spend on buying and selling capital items — "
        "land, machinery, quota — on average per farm."
    ),

    # ── Household income ──────────────────────────────────────────────
    "32-10-0213-01": (
        "Income of farm families from all sources — farm earnings, "
        "off-farm employment, investments, and government transfers — "
        "showing the full household financial picture."
    ),
    "32-10-0214-01": (
        "Farm family income broken into quartiles (bottom 25%, middle, "
        "top 25%) — highlighting the income gap between the most and "
        "least prosperous farm households."
    ),

    # ── Census 2021 snapshots ─────────────────────────────────────────
    "32-10-0237-01": (
        "Census snapshot of total farm capital — land, buildings, "
        "equipment, and livestock value — as reported in the 2021 "
        "Census of Agriculture."
    ),
    "32-10-0238-01": (
        "Detailed count and value of farm machinery — tractors, "
        "combines, seeders — from the 2021 Census of Agriculture."
    ),
    "32-10-0239-01": (
        "Distribution of farms by revenue bracket — how many farms "
        "earn under $10K, $10K–$50K, $50K–$100K, etc. — from the "
        "2021 Census."
    ),
    "32-10-0240-01": (
        "Total operating revenues reported by farms in the 2021 "
        "Census — the gross income side of the farming business."
    ),
    "32-10-0241-01": (
        "Total operating expenses reported by farms in the 2021 "
        "Census — the cost side of the farming business."
    ),
    "32-10-0242-01": (
        "How many farms sell directly to consumers — at farm gates, "
        "farmers' markets, or online — and the types of products "
        "sold, from the 2021 Census."
    ),
    "32-10-0235-01": (
        "How farms are legally organized — sole proprietorships, "
        "partnerships, family corporations, or non-family corporations "
        "— from the 2021 Census."
    ),
    "32-10-0243-01": (
        "Counts of paid agricultural workers — full-time, part-time, "
        "and seasonal — from the 2021 Census. Shows the structure "
        "of the farm labour force."
    ),

    # ── Farm structure & land ─────────────────────────────────────────
    "32-10-0157-01": (
        "Historical Census data showing how many farms fall into each "
        "revenue bracket (under $10K, $10K–$25K, etc.) — tracking "
        "farm size distribution over decades."
    ),
    "32-10-0163-01": (
        "Historical Census data counting farm machinery — tractors "
        "by horsepower, combines, and other equipment — going back "
        "as far as 1921."
    ),
    "32-10-0166-01": (
        "Number of farms classified by NAICS industry code — oilseed, "
        "dairy, greenhouse, etc. — showing the composition of "
        "Canada's farming sector."
    ),
    "32-10-0157-01": (
        "Historical data on how many farms fall into each gross "
        "revenue bracket — tracking whether farms are consolidating "
        "into fewer, larger operations over time."
    ),

    # ── Demographics & labour ─────────────────────────────────────────
    "32-10-0036-01": (
        "Tracks fertilizer shipments by product type (urea, ammonia, "
        "phosphate, potash, etc.) in metric tonnes — an indicator "
        "of input demand and cropping intensity."
    ),
    "32-10-0156-01": (
        "Historical Census data on farm size — how many farms fall "
        "into each acreage bracket — showing whether land is "
        "consolidating into larger operations."
    ),
    "32-10-0215-01": (
        "Counts of employees in agriculture broken down by industry "
        "sub-group (beef, dairy, hog, greenhouse, etc.)."
    ),
    "32-10-0218-01": (
        "Temporary foreign workers (TFWs) employed in agriculture "
        "and agri-food, broken down by industry sector."
    ),
    "32-10-0220-01": (
        "Temporary foreign workers in agriculture by revenue class "
        "of the hiring farm — showing how reliance on TFWs varies "
        "with farm size."
    ),
    "32-10-0221-01": (
        "Temporary foreign workers by country of citizenship — "
        "Mexico, Jamaica, Guatemala, and others — showing where "
        "Canada's seasonal farm labour comes from."
    ),
    "32-10-0379-01": (
        "Adoption of farming technologies — GPS guidance, precision "
        "agriculture, drones, robotics — by farm type."
    ),

    # ── Costs & inflation ─────────────────────────────────────────────
    "18-10-0258-01": (
        "The Farm Input Price Index (FIPI) — tracks how much farmers "
        "pay for inputs like fuel, fertilizer, seed, and machinery. "
        "Rising values mean farming is getting more expensive."
    ),
    "18-10-0258-02": (
        "Year-over-year percentage change in the Farm Input Price "
        "Index — showing how fast farming costs are rising or "
        "falling compared to the previous year."
    ),
    "18-10-0270-01": (
        "Machinery and equipment price index — tracks how purchase "
        "prices for farm equipment change over time."
    ),
    "32-10-0098-01": (
        "Market prices received by farmers for their products — "
        "crops, livestock, dairy — showing what the market pays "
        "at the farm gate."
    ),
    "32-10-0077-01": (
        "Farm product prices at the point of sale — what producers "
        "actually receive for their crops and livestock."
    ),
    "18-10-0004-03": (
        "Consumer Price Index for food — tracks how grocery store "
        "prices change over time, which affects consumer demand "
        "and farmer revenues downstream."
    ),

    # ── Production & yields ───────────────────────────────────────────
    "32-10-0003-01": (
        "Canada's on-farm grain and oilseed storage capacity — in "
        "metric tonnes and bushels — an indicator of harvest "
        "logistics and marketing flexibility."
    ),
    "32-10-0359-01": (
        "Crop production estimates — area seeded, area harvested, "
        "average yield, and total production — for major field crops."
    ),
    "32-10-0130-01": (
        "Livestock inventory counts — cattle, hogs, sheep — tracked "
        "over time to show herd size trends."
    ),

    # ── Transportation & exports ──────────────────────────────────────
    "18-10-0281-01": (
        "Freight trucking price index — tracks shipping costs for "
        "moving agricultural products by road."
    ),
    "18-10-0212-01": (
        "Freight rail services price index by commodity group — "
        "tracks the cost of shipping grain, potash, and other bulk "
        "commodities by rail."
    ),

    # ── Agri-Food Exports ─────────────────────────────────────────────
    "12-10-0175-01": (
        "Canadian International Merchandise Trade by province, commodity "
        "(HS section), and principal trading partner — filtered to agri-food "
        "sectors (HS Sections I–IV). Tracks export and import values in "
        "thousands of Canadian dollars."
    ),
    "12-10-0163-01": (
        "International merchandise trade by commodity, monthly. Provides detailed "
        "NAPCS commodity breakdown (wheat, canola, meat, dairy, beverages, etc.) "
        "for Canada's imports and exports. Used in the Agri-Food Exports page for "
        "national-level commodity analysis."
    ),

    # ── Environment & land use ────────────────────────────────────────
    "38-10-0259-01": (
        "Tracks the volume of water used for crop irrigation across "
        "Canada — a key indicator of water demand in agriculture."
    ),

    # ── OMAFRA commodity prices ───────────────────────────────────────
    "omafra-average-weekly-corn-prices": (
        "Weekly average corn prices in Ontario — a key reference "
        "price for feed costs, ethanol production, and the broader "
        "grain market."
    ),
    "omafra-average-weekly-soybean-prices": (
        "Weekly average soybean prices in Ontario — soybeans are "
        "Ontario's highest-value field crop and a major export."
    ),
    "omafra-average-weekly-wheat-prices": (
        "Weekly average wheat prices in Ontario — tracking the "
        "market value of Canada's most widely grown cereal crop."
    ),

    # ── Dairy ──────────────────────────────────────────────────────────
    "32-10-0113-01": (
        "Monthly milk production and utilization — how much milk "
        "Canadian farms produce, and how it's split between fluid "
        "consumption and industrial processing (cheese, butter, etc.)."
    ),
    "32-10-0114-01": (
        "Commercial sales of milk and cream by province — revenue "
        "and volume flowing through Canada's supply-managed dairy "
        "system each month."
    ),

    # ── Poultry & Eggs ─────────────────────────────────────────────────
    "32-10-0117-01": (
        "Poultry meat production and farm value — how much chicken "
        "and turkey Canada produces, and what it's worth at the "
        "farm gate."
    ),
    "32-10-0121-01": (
        "Monthly egg production and disposition — how many eggs "
        "Canadian farms produce, where they go (processing, retail, "
        "export), and what price producers receive."
    ),
    "32-10-0123-01": (
        "Monthly chick and turkey poult placements — a forward-looking "
        "indicator of future poultry meat and egg supply. More "
        "placements today mean more production in weeks ahead."
    ),
    "32-10-0133-01": (
        "Cold storage stocks of frozen poultry meats — how much "
        "chicken and turkey is sitting in Canadian freezers. High "
        "stocks may signal oversupply or weak demand."
    ),

    # ── Aquaculture ────────────────────────────────────────────────────
    "32-10-0107-01": (
        "Canada's aquaculture production and value — farmed salmon, "
        "mussels, oysters, and other species — tracking the growth "
        "of this $1.3 billion industry by province."
    ),
    "32-10-0005-01": (
        "Canadian aquaculture exports by destination — where Canada "
        "ships its farmed seafood (mainly Atlantic salmon) and how "
        "much each market is worth."
    ),

    # ── Sheep & Lambs ──────────────────────────────────────────────────
    "32-10-0129-01": (
        "Semi-annual sheep and lamb inventories by province — "
        "completing the livestock picture alongside cattle and hog "
        "counts, tracking flock size trends."
    ),

    # ── Phase 2: Cattle & Hog Detail ───────────────────────────────────
    "32-10-0125-01": (
        "Cattle and calf production — how many animals were raised "
        "and how much meat was produced, by province. Pairs with "
        "cattle inventory data to show the full beef pipeline."
    ),
    "32-10-0139-01": (
        "Cattle supply and disposition — tracks the full flow from "
        "beginning stocks through births, imports, slaughter, "
        "exports, and deaths to ending stocks."
    ),
    "32-10-0141-01": (
        "Sheep and lamb supply and disposition — the full supply "
        "chain from beginning inventory through births, slaughter, "
        "and trade to ending stocks."
    ),
    "32-10-0137-01": (
        "Cold storage stocks of frozen and chilled red meats — beef, "
        "pork, and lamb sitting in Canadian warehouses. A key "
        "indicator of supply pressure and market balance."
    ),
    "32-10-0002-01": (
        "Pre-harvest and in-season crop estimates — area seeded, "
        "expected yield, and projected production for major field "
        "crops. A forward-looking companion to final harvest data."
    ),
    "32-10-0151-01": (
        "Number of cattle farms and average herd size by province — "
        "tracking whether the beef sector is consolidating into "
        "fewer, larger operations over time."
    ),
    "32-10-0202-01": (
        "Number of hog farms and average herd size by province — "
        "a consolidation indicator for Canada's pork sector, "
        "showing structural change in farm scale."
    ),

    # ── Phase 2: Grain Stocks ──────────────────────────────────────────
    "32-10-0007-01": (
        "Quarterly on-farm and commercial grain stocks by crop and "
        "province — showing how much grain is sitting in storage. "
        "High stocks can signal price pressure; low stocks signal tightness."
    ),

    # ── Phase 2: Fertilizer & Pesticide Use ────────────────────────────
    "32-10-0408-01": (
        "Census of Agriculture snapshot of chemical input use — "
        "what share of farms apply fertilizers, herbicides, "
        "insecticides, and fungicides, by province."
    ),

    # ── Phase 3: Census Crop Snapshots ─────────────────────────────────
    "32-10-0309-01": (
        "Census 2021 snapshot of field crop and hay acreage at the "
        "census-division level — the most granular geographic data "
        "available for seeded area."
    ),
    "32-10-0315-01": (
        "Census 2021 fruit-bearing acreage at census-division level — "
        "apples, blueberries, strawberries, grapes, and other "
        "orchard and berry crops."
    ),
    "32-10-0355-01": (
        "Census 2021 field vegetable acreage at census-division level — "
        "sweet corn, tomatoes, carrots, onions, and other "
        "open-field vegetable crops."
    ),
    "32-10-0360-01": (
        "Census 2021 greenhouse product area at census-division level — "
        "flowers, nursery products, vegetables, and other "
        "controlled-environment crops."
    ),

    # ── Phase 3: Census Poultry & Egg Snapshots ────────────────────────
    "32-10-0374-01": (
        "Census 2021 poultry flock counts at census-division level — "
        "chickens, turkeys, and other poultry by geographic area."
    ),
    "32-10-0375-01": (
        "Census 2021 poultry meat production at census-division level — "
        "a point-in-time snapshot complementing the annual series."
    ),
    "32-10-0376-01": (
        "Census 2021 egg production at census-division level — "
        "a point-in-time snapshot complementing the monthly series."
    ),

    # ── Phase 3: Census Sheep Snapshot ─────────────────────────────────
    "32-10-0371-01": (
        "Census 2021 sheep and lamb counts at census-division level — "
        "the most geographically detailed sheep inventory data available."
    ),

    # ── Phase 3: Food Manufacturing ────────────────────────────────────
    "16-10-0048-01": (
        "Monthly manufacturing sales by subsector — filter for "
        "NAICS 311 (Food) to track food manufacturing revenue. "
        "Extends the value chain beyond the farm gate."
    ),

    # ── Capital Investment & Productivity ─────────────────────────────
    "36-10-0096-01": (
        "Shows how much **new money** is invested each year in agriculture "
        "and food manufacturing — spending on buildings, machinery, equipment, "
        "and intellectual property. The default view ('Investment' under "
        "'Flows and stocks') shows the annual flow of new capital spending, "
        "not the total accumulated capital stock. To see the cumulative value "
        "of all capital assets, switch 'Flows and stocks' to 'End-year gross "
        "stock'. Note: values in 'Current prices' are nominal (not adjusted "
        "for inflation); switch to '2017 constant prices' under 'Prices' for "
        "a real comparison across decades."
    ),
    "36-10-0488-01": (
        "Gross output of industries — the total value of goods produced. "
        "When filtered to food manufacturing (NAICS 311), this shows how "
        "much value-added processing Canada does domestically. Rising output "
        "signals a growing food sector; flat output suggests Canada may be "
        "exporting raw commodities instead of processed products."
    ),
    "36-10-0434-03": (
        "Agriculture's contribution to Canada's GDP at basic prices — showing "
        "what farming and food manufacturing are worth to the national economy. "
        "Unlike gross output, GDP measures only the **value added** by each "
        "industry (output minus intermediate inputs like feed and fertilizer). "
        "Use this to compare agriculture's economic weight against other sectors."
    ),
    "36-10-0217-01": (
        "Multifactor productivity in agriculture — how efficiently capital "
        "and labour combine to produce output. An index above 100 means the "
        "sector is producing more with the same inputs. Canada's ag "
        "productivity growth peaked in the 1990s–2000s and has slowed since, "
        "signaling an underinvestment problem that limits future output growth."
    ),
    "32-10-0398-01": (
        "Farm operators classified by farm type and place of birth (Census 2021). "
        "Shows counts of immigrant operators, operators born in Canada, and "
        "operators born outside Canada by geography and farm type."
    ),
}
