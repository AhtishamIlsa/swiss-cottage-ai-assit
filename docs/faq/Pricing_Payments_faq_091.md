---
category: Pricing & Payments
faq_id: faq_091
intent: pricing
optional_slots:
- season
question: What payment methods do you accept?
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

Question: What payment methods do you accept?

Answer: We accept bank transfers and cash payments. A partial payment is required at the time of booking to confirm the reservation, and the remaining amount is paid at the time of check-in.
