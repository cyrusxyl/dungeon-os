---
name: Social Encounters & Interaction
description: Handle D&D 5e social encounters including persuasion, deception, intimidation, insight, and NPC relationships. Use when players negotiate, lie, threaten, or interact with NPCs. Tracks relationships, language barriers, and social dynamics.
---

# Social Encounters & Interaction

Manage roleplay-heavy encounters with API-sourced skill mechanics, relationship tracking, and language systems.

## Social Skill Checks

When players engage in social interaction:

### Persuasion

**Use for**: Convincing, negotiating, diplomacy, inspiring

**Query skill**:
```bash
curl -sL "https://www.dnd5eapi.co/api/2014/skills/persuasion" | jq '{
  name: .name,
  desc: .desc,
  ability_score: .ability_score.name
}'
```

**Ability**: Charisma

**Examples**:
- Convincing guards to let you pass
- Negotiating a better price
- Rallying townspeople to your cause
- Making a formal request to nobility

**DCs**:
- Friendly NPC, reasonable request: DC 10
- Neutral NPC, easy request: DC 15
- Unfriendly NPC, difficult request: DC 20
- Hostile NPC, nearly impossible request: DC 25

**Modifiers**:
- Good argument or roleplay: Advantage or -5 DC
- Poor argument or offensive: Disadvantage or +5 DC
- NPC already likes party: -2 to -5 DC
- NPC dislikes party: +2 to +5 DC

### Deception

**Use for**: Lying, disguising, creating false impressions

**Query skill**:
```bash
curl -sL "https://www.dnd5eapi.co/api/2014/skills/deception" | jq '{
  name: .name,
  desc: .desc,
  ability_score: .ability_score.name
}'
```

**Ability**: Charisma

**Examples**:
- Lying about your identity
- Bluffing in a game
- Creating a false alibi
- Disguising your intentions

**Contested**: Usually opposed by target's Insight

**Process**:
1. Player makes Deception check
2. NPC makes Insight check
3. If Deception ≥ Insight: NPC believes lie
4. If Deception < Insight: NPC sees through deception

**Consequences of failed Deception**:
- NPC becomes hostile or suspicious
- NPC alerts others
- Future interactions with this NPC have disadvantage

### Intimidation

**Use for**: Threatening, coercing, frightening

**Query skill**:
```bash
curl -sL "https://www.dnd5eapi.co/api/2014/skills/intimidation" | jq '{
  name: .name,
  desc: .desc,
  ability_score: .ability_score.name
}'
```

**Ability**: Charisma (sometimes Strength at DM discretion)

**Examples**:
- Threatening a captive for information
- Coercing a merchant to lower prices
- Scaring away weak enemies
- Extorting protection money

**DCs**:
- Weak-willed or fearful NPC: DC 10
- Average NPC: DC 15
- Strong-willed or brave NPC: DC 20
- Fearless or immune to fear: Auto-fail

**Modifiers**:
- Display of force (drawn weapon, show of strength): Advantage
- Empty threat or unconvincing: Disadvantage
- Size difference (larger intimidating smaller): -5 DC

**Consequences**:
- Success: NPC complies out of fear, may resent you
- Failure: NPC resists, may turn hostile
- Critical failure: NPC calls for help or attacks

### Insight

**Use for**: Detecting lies, reading intentions, sensing emotions

**Query skill**:
```bash
curl -sL "https://www.dnd5eapi.co/api/2014/skills/insight" | jq '{
  name: .name,
  desc: .desc,
  ability_score: .ability_score.name
}'
```

**Ability**: Wisdom

**Examples**:
- Detecting if NPC is lying
- Sensing hidden motives
- Reading body language
- Determining if someone is trustworthy

**Contested**: Opposed by target's Deception

**Passive Insight**: 10 + Insight modifier, used to automatically detect obvious lies or suspicious behavior

**Result on success**:
- "The merchant's eyes dart nervously when he mentions the price. He's hiding something."
- "The guard's hand moves to his sword hilt. He's expecting trouble."
- "She seems genuinely distressed. Her tears are real."

### Performance

**Use for**: Entertaining, acting, artistic displays

**Query skill**:
```bash
curl -sL "https://www.dnd5eapi.co/api/2014/skills/performance" | jq '{
  name: .name,
  desc: .desc,
  ability_score: .ability_score.name
}'
```

**Ability**: Charisma

**Examples**:
- Performing music for a crowd
- Acting in a play
- Telling a story dramatically
- Creating a distraction through performance

**DCs**:
- Routine performance: DC 10
- Memorable performance: DC 15
- Exceptional performance: DC 20
- Legendary performance: DC 25

**Rewards for successful performance**:
- Tips: 1d10 sp (DC 10), 1d10 gp (DC 15), 2d10 gp (DC 20)
- Reputation: NPCs recognize you, gain favor
- Information: NPCs share gossip or rumors

## NPC Relationships

Track how NPCs feel about the party:

### Relationship Status

**Hostile**: Will attack on sight or actively work against party
**Unfriendly**: Won't help, may hinder, suspicious
**Neutral**: Indifferent, transactional
**Friendly**: Helpful, willing to assist
**Allied**: Loyal, will take risks to help party

### Updating Relationships

After significant interactions, update NPC file:

```json
{
  "name": "Sildar Hallwinter",
  "relationship_to_party": "allied",
  "notes": "Session 1: Party rescued from goblins. Session 2: Party helped clear Redbrand threat. Very grateful and loyal."
}
```

**Relationship changes**:
- Helping NPC: Unfriendly → Neutral, Neutral → Friendly, Friendly → Allied
- Harming NPC: Any status → Hostile
- Ignoring NPC's request: May decrease by one step
- Betraying NPC: Any status → Hostile permanently

### Reaction Rolls

For new NPCs without established relationship:

```bash
source .venv/bin/activate && roll 2d6+{charisma_modifier} -v
```

**Result**:
- 2-4: Hostile
- 5-7: Unfriendly
- 8-11: Neutral
- 12-14: Friendly
- 15+: Allied

**Modifiers**:
- Party has good reputation: +2
- Party has bad reputation: -2
- NPC's faction allied with party: +2
- NPC's faction opposed to party: -2

## Language Barriers

### Languages in D&D

**Query language details**:
```bash
curl -sL "https://www.dnd5eapi.co/api/2014/languages/{language-index}" | jq '{
  name: .name,
  desc: .desc,
  type: .type,
  typical_speakers: .typical_speakers,
  script: .script
}'
```

**Common languages**:
- **Common**: Trade tongue, most humanoids speak it
- **Dwarvish**: Dwarves
- **Elvish**: Elves
- **Giant**: Giants, ogres
- **Gnomish**: Gnomes
- **Goblin**: Goblinoids
- **Halfling**: Halflings
- **Orc**: Orcs

**Exotic languages**:
- **Abyssal**: Demons
- **Celestial**: Angels
- **Draconic**: Dragons, dragonborn
- **Deep Speech**: Aberrations, mind flayers
- **Infernal**: Devils
- **Primordial**: Elementals (includes Aquan, Auran, Ignan, Terran)
- **Sylvan**: Fey
- **Undercommon**: Underdark traders

### Handling Language Barriers

**When NPC doesn't speak Common**:

1. **Check character languages**: Read character file for known languages
2. **Find translator**: Another party member who speaks the language
3. **Use magic**: *Comprehend Languages*, *Tongues*
4. **Pantomime**: Charisma check (DC 15) to communicate basic concepts

**Example**:
> DM: "The dwarf addresses you in Dwarvish, gesturing urgently at the cave."
> Player: "Does anyone speak Dwarvish?"
> DM: *checks character files* "No one in the party knows Dwarvish."
> Player: "Can I tell what he's trying to communicate?"
> DM: "Make a Wisdom (Insight) check."
> *rolls 16*
> DM: "You can tell he's warning you about something dangerous in the cave, but you don't understand the specifics."

### Learning Languages

**Downtime training**:
- Time: 10 weeks minus INT modifier (minimum 2 weeks)
- Cost: 25 gp per week for teacher
- Result: Add language to character's known languages

**Magic**:
- *Comprehend Languages* (1st-level): Understand any language for 1 hour
- *Tongues* (3rd-level): Understand and speak any language for 1 hour

## Negotiation & Bartering

### Haggling

When players try to negotiate prices:

**Process**:
1. Player makes Persuasion check
2. Merchant makes opposed Persuasion or Insight check
3. Compare results

**Outcomes**:
- Player wins by 5+: 10% discount
- Player wins by 10+: 20% discount
- Player wins by 15+: 25% discount
- Tie or close: No change
- Merchant wins: No discount, may increase price or refuse service

**Modifiers**:
- Buying in bulk: +2 to player's check
- Merchant needs the sale: +5 to player's check
- Rare or unique item: -5 to player's check
- Player has high reputation: +2 to player's check

### Making Deals

When negotiating terms of an agreement:

**Structure**:
1. **What does each party want?** Define goals
2. **What can each party offer?** Identify bargaining chips
3. **What's the BATNA?** (Best Alternative To Negotiated Agreement)

**Persuasion check**:
- DC 10: Fair deal, both benefit
- DC 15: Favorable deal, party benefits more
- DC 20: Very favorable deal, party wins big
- Failure: No deal, or NPC's terms

**Consequences of breaking deals**:
- Reputation damage
- NPC becomes hostile
- Legal repercussions (fines, imprisonment)

## Information Gathering

### Rumors & Gossip

When players want to learn information:

**Methods**:
- Persuasion: Buy drinks, make friends, ask nicely
- Deception: Pretend to be someone else, fish for info
- Intimidation: Threaten or coerce
- Investigation: Search records, notice boards
- Insight: Read between the lines

**DCs**:
- Common knowledge: DC 10
- Uncommon knowledge: DC 15
- Secret information: DC 20
- Closely guarded secret: DC 25

**Rolling for rumors**:
```bash
source .venv/bin/activate && roll 1d8 -v
```

Create rumor table:
1. False rumor, misleading
2-3. Partially true, distorted
4-6. True information
7. True with bonus detail
8. Major plot revelation

### Interrogation

When questioning a captive or witness:

**Approach**:
- **Friendly** (Persuasion): "We just want to help you"
- **Deceptive** (Deception): "Your partner already told us everything"
- **Intimidating** (Intimidation): "Talk or suffer the consequences"

**Contested check**: Player's skill vs NPC's Wisdom save or Deception

**Success levels**:
- Failure: NPC refuses to talk or lies
- Success: NPC provides basic information
- Success by 5+: NPC provides detailed information
- Success by 10+: NPC reveals everything, including secrets

**Repeated interrogation**: Each failed attempt increases DC by 2

## Social Encounters in Combat

### Parley

When trying to avoid or stop combat:

**Timing**: Before initiative or during initiative (uses action)

**Check**: Persuasion, Deception, or Intimidation

**DCs**:
- Intelligent enemies with clear goals: DC 15
- Mindless or enraged enemies: DC 25 or impossible
- Enemies winning the fight: +5 DC
- Enemies losing the fight: -5 DC

**Success**: Enemies agree to talk, cease hostilities temporarily

**Failure**: Combat continues, enemies may become more aggressive

### Surrender

When offering or demanding surrender:

**Player surrender**: No check, enemies choose to accept or reject

**Enemy surrender**: Intimidation check vs enemy morale
- DC based on enemy intelligence and remaining HP
- Intelligent enemies at <50% HP: DC 15
- Mindless or fanatical enemies: Auto-fail

## Role-Playing vs. Rolling

**Balance approach**:
- Good roleplay can grant advantage or reduce DC
- Automatic success if roleplay is exceptional and task is reasonable
- Always roll for high-stakes or contested situations
- Don't punish players for being shy, allow rolling instead of acting

**Example**:
- Player gives compelling speech: Grant advantage on Persuasion
- Player has no idea what to say: Roll straight Persuasion, narrate based on result

## Tracking Social Connections

Update campaign state with NPC relationships:

**In NPC files** (`{campaign}/world/npcs/{name}.json`):
```json
{
  "relationship_to_party": "friendly",
  "favor_owed": "Party saved his daughter",
  "last_interaction": "Session 3",
  "notes": "Will help party with information about Black Spider if asked"
}
```

**In state file** (`{campaign}/state.json`):
```json
{
  "faction_reputation": {
    "lords_alliance": 5,
    "zhentarim": -3,
    "harpers": 2
  }
}
```

## API Endpoints Reference

**Skills**:
- Persuasion: `GET /api/2014/skills/persuasion`
- Deception: `GET /api/2014/skills/deception`
- Intimidation: `GET /api/2014/skills/intimidation`
- Insight: `GET /api/2014/skills/insight`
- Performance: `GET /api/2014/skills/performance`

**Languages**:
- List: `GET /api/2014/languages`
- Details: `GET /api/2014/languages/{index}`

## Tips

- **Say yes, and...**: Build on player ideas, don't shut down creative approaches
- **Let players roleplay**: Don't force dice rolls for every interaction
- **Read the room**: If players are engaged in roleplay, let it flow
- **Consequences matter**: Failed social checks should have meaningful outcomes
- **NPCs remember**: Track interactions and let NPCs react based on history
- **Multiple approaches**: There's always more than one way to solve a social problem

## Common Mistakes to Avoid

- **Don't make everything a check**: Let simple interactions happen naturally
- **Don't punish bad roleplay**: Some players are shy, use dice to help them
- **Don't ignore failure**: Failed social checks should complicate situations
- **Don't let Charisma solve everything**: Some NPCs can't be persuaded
- **Don't forget NPC motivations**: NPCs should act according to their goals, not player desires
- **Don't skip consequences**: Intimidation may work now but create enemies later

## Integration with Other Skills

- **Worldbuilding** → Generate NPCs with personalities and motivations
- **Exploration** → Insight checks to detect ambush, Persuasion to get directions
- **Combat** → Intimidation to demoralize enemies, Persuasion to avoid fights
- **Magic** → Spells like *Charm Person*, *Suggestion*, *Zone of Truth*
