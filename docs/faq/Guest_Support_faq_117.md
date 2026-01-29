---
category: Guest Support
faq_id: faq_117
intent: booking
optional_slots:
- season
question: Is there an on-site caretaker available during the stay?
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

Category: Guest Support

Question: Is there an on-site caretaker available during the stay?

Answer: Yes, an on-site caretaker is available to assist guests with check-in, orientation, and any basic needs during their stay.
