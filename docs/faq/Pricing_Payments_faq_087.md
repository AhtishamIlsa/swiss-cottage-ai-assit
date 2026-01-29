---
category: Pricing & Payments
faq_id: faq_087
intent: pricing
optional_slots:
- season
question: How many bedrooms and bathrooms are in each cottage?
required_slots:
- guests
- dates
- room_type
slot_extraction_hints: "  guests: number of guests or people\n  dates: check-in and\
  \ check-out dates\n  room_type: cottage 7, 9, or 11\n  season: weekday, weekend,\
  \ peak, or off-peak"
source: Google Sheets
type: qa_pair
---

Category: Pricing & Payments

Question: How many bedrooms and bathrooms are in each cottage?

Answer: Each 3-bedroom cottage has one bedroom with an attached bathroom, while the remaining two bedrooms share a common bathroom.
