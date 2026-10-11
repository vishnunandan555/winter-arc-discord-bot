"""
ai/fallbacks.py - Curated Quotes and Deterministic Fallback Data
"""

CURATED_STOIC_FALLBACKS = [
    "The iron does not negotiate with your mood. Move.",
    "Words build nothing. Numbers on the board are the only truth.",
    "Discipline is choosing between what you want now and what you want most.",
    "Consistency beats intensity every single time.",
    "A 7-day streak means nothing if you drop the standard today.",
    "Excuses don't burn calories or write code. Log the work.",
    "Small daily disciplines compound into undeniable results.",
    "The scoreboard doesn't lie. Put in the work before midnight.",
]

AUTHENTIC_STOIC_QUOTES = [
    '"Waste no more time arguing what a good man should be. Be one." — Marcus Aurelius',
    '"You have power over your mind - not outside events. Realize this, and you will find strength." — Marcus Aurelius',
    '"The impediment to action advances action. What stands in the way becomes the way." — Marcus Aurelius',
    '"Dwell on the beauty of life. Watch the stars, and see yourself running with them." — Marcus Aurelius',
    '"We suffer more often in imagination than in reality." — Seneca',
    '"Luck is what happens when preparation meets opportunity." — Seneca',
    '"It is not because things are difficult that we do not dare; it is because we do not dare that they are difficult." — Seneca',
    '"No person is free who is not master of oneself." — Epictetus',
    '"Don\'t explain your philosophy. Embody it." — Epictetus',
    '"How long are you going to wait before you demand the best for yourself?" — Epictetus',
    '"Difficulties show a person\'s character." — Epictetus',
]

AUTHENTIC_REST_QUOTES = [
    '"He who knows when he can fight and when he cannot, will be victorious." — Sun Tzu',
    '"Even a bow breaks if it is kept always bent." — Publilius Syrus',
    '"Take rest; a field that has rested gives a bountiful crop." — Ovid',
    '"In intervals of rest, the mind and body find renewed vigor." — Seneca',
    '"No man is free who is not master of himself." — Epictetus',
    '"Nature does not hurry, yet everything is accomplished." — Lao Tzu',
    '"Rest when you are weary. Refresh and renew yourself, your body, your mind, your spirit." — Marcus Aurelius',
]

ARD_AFTERNOON_FALLBACKS = [
    "Midday check-in, warriors. Fun fact: light walking stimulates the lymphatic system—which has no central pump of its own—clearing out metabolic waste 3x faster than sitting still. Drink a tall glass of water, stretch your hips, and get 15 minutes of light sun.",
    "Step away from your screen for ten minutes. Did you know tendons and ligaments take up to 10x longer to remodel than muscle tissue because of lower blood flow? Active recovery movement is what forces nutrients into them. Hydrate well, eat clean fuel, and stay mobile.",
    "Midday pulse check. Dehydration reduces muscular endurance by up to 15% before you even feel thirsty. Chug 500ml of water right now, eat a nutrient-dense meal, and loosen up tight hamstrings and shoulders.",
    "Your central nervous system (CNS) requires 48 hours to fully reset after heavy training strain. Active recovery with gentle mobility signals your parasympathetic system to begin cellular repair. Keep the blood moving lightly today.",
]

ARD_EVENING_FALLBACKS = [
    "Active Recovery Day is coming to a close, and all streaks are safely preserved. Growth hormone production peaks during stage 3 deep slow-wave sleep—so shut off screens early and get to bed. Tomorrow morning we hunt at 100% intensity.",
    "The pack observed recovery today. Your muscles repaired, joints settled, and your energy is topped off. Disconnect from devices, get 8 hours of restorative sleep, and prepare your mindset. We attack at dawn.",
    "Active recovery is complete. True strength is built in the dark while you rest, not just when you grind. Wind down your evening, sleep deep, and wake up hungry tomorrow. Tomorrow we go full throttle.",
]


def get_default_callout(points: int) -> str:
    """Returns the default, grounded 1-sentence accountability callout based on points."""
    if points == 0:
        return "0 pts on the board. Stop scrolling, drop and get your 30 push-ups in before your streak breaks tonight."
    elif points < 30:
        needed = 30 - points
        return f"{points} pts on the board. You need {needed} more points before midnight to save your streak."
    elif points >= 500:
        return f"{points} pts, completely maxed out the board early. Rest up for tomorrow."
    else:
        return f"{points} pts, streak is safe! Solid execution, but see if you can squeeze in another set before midnight."
