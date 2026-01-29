---
category: Cancellation & Refunds
faq_id: faq_104
intent: booking
optional_slots:
- season
question: Is the cancellation policy different for direct bookings and Airbnb bookings?
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

Category: Cancellation & Refunds

Question: Is the cancellation policy different for direct bookings and Airbnb bookings?

Answer: Yes, Airbnb bookings follow Airbnb’s cancellation policies, while direct bookings follow the terms shared by management at the time of confirmation. Guests are encouraged to confirm the applicable policy before booking.
