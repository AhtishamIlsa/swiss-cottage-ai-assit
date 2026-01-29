---
category: Check-in & Check-out
faq_id: faq_107
intent: booking
optional_slots:
- season
question: How do guests check in at the cottage?
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

Question: How do guests check in at the cottage?

Answer: After booking confirmation, guests receive the caretaker’s contact details. Guests are requested to contact the caretaker approximately one hour before arrival, and the caretaker assists with check-in and access to the cottage.
