---
category: Verification & Compliance
faq_id: faq_111
intent: booking
optional_slots:
- season
question: Is guest verification required?
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

Category: Verification & Compliance

Question: Is guest verification required?

Answer: Guests may be asked to provide valid identification at booking or check-in as part of standard security and community guidelines.
