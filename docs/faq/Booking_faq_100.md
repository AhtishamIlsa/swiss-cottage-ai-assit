---
category: Booking
faq_id: faq_100
intent: booking
optional_slots:
- season
question: Do you provide booking confirmation?
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

Question: Do you provide booking confirmation?

Answer: Yes, once the booking is confirmed, you receive a clear confirmation message with stay details and check-in instructions.
