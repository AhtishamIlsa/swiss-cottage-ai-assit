---
category: Booking
faq_id: faq_099
intent: booking
optional_slots:
- season
question: What details are required to book?
required_slots:
- guests
- dates
- room_type
- family
slot_extraction_hints: "  guests: number of guests or people\n  dates: check-in and\
  \ check-out dates\n  room_type: cottage 7, 9, or 11\n  family: whether booking is\
  \ for family or friends\n  season: weekday, weekend, peak, or off-peak"
source: Google Sheets
type: qa_pair
---

Category: Booking

Question: What details are required to book?

Answer: To confirm a booking, we need your dates, number of guests, whether the stay is for family or friends, and your preferred cottage.
