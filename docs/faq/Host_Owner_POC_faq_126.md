---
category: Host / Owner / POC
faq_id: faq_126
intent: booking
optional_slots:
- season
question: Who is the point of contact?
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

Category: Host / Owner / POC

Question: Who is the point of contact?

Answer: The primary point of contact is the host and the on-site caretaker, whose contact details are shared after booking confirmation.
