---
category: Check-in & Check-out
faq_id: faq_108
intent: booking
optional_slots:
- season
question: Is early check-in or late check-out available?
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

Category: Check-in & Check-out

Question: Is early check-in or late check-out available?

Answer: Early check-in or late check-out may be possible depending on availability and should be requested in advance.
