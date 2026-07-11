/* ============================================================
   SikaSafe — scam-message analyzer
   Transparent heuristics. Runs 100% on the phone; the text you
   paste never leaves the device. Every verdict lists the exact
   red flags it matched, so it teaches while it checks.
   ============================================================ */
(function () {
'use strict';

/* Each rule: a category, a weight, whether it alone is damning
   (critical), the patterns to match, the red flag it represents,
   and the advice to give. */
const RULES_DETECT = [
  {
    id: 'ask-pin-otp', cat: 'agent', weight: 6, critical: true,
    re: [/\bpin\b/i, /\botp\b/i, /one[\s-]?time (code|password|pin)/i,
         /verification code/i, /secret code/i, /confirm your (pin|code|password)/i,
         /share (the |your )?(code|pin|otp)/i, /enter your pin/i],
    flag: { en: 'It asks for your PIN or a one-time code (OTP).',
            pcm: 'E dey ask your PIN or one-time code (OTP).' },
    advice: { en: 'No genuine person or company ever needs these. Do not share them. This is the #1 sign of fraud.',
              pcm: 'No genuine person or company dey ever need dis. No share am. Na the #1 sign of fraud.' },
  },
  {
    id: 'dial-code', cat: 'code', weight: 5, critical: true,
    re: [/dial\s*\*?\d/i, /\*\d{2,}[\d*]*#/, /press\s*\d/i, /dial (the|this) code/i,
         /enter (the|this) code/i],
    flag: { en: 'It tells you to dial or enter a code.',
            pcm: 'E tell you make you dial or enter code.' },
    advice: { en: 'A code someone gives you can secretly approve a payment or move your money. Never dial codes from strangers.',
              pcm: 'Code wey person give you fit secretly approve payment or move your money. No dial code from strangers.' },
  },
  {
    id: 'reverse', cat: 'reverse', weight: 4,
    re: [/revers/i, /wrong (number|transfer|account|send)/i, /sent (it|you|to you)?.{0,20}(mistake|error|by accident|wrongly)/i,
         /send (it |the money )?back/i, /return the (money|cash|funds)/i, /mistakenly (sent|paid)/i,
         /by mistake/i],
    flag: { en: 'It talks about a “wrong” transfer and sending money back.',
            pcm: 'E dey talk about “wrong” transfer and send money back.' },
    advice: { en: 'Check your REAL balance first. A fake “credit” SMS is the classic trap — never send money back on trust.',
              pcm: 'Check your REAL balance first. Fake “credit” SMS na the classic trap — no send money back on trust.' },
  },
  {
    id: 'won', cat: 'promo', weight: 3,
    re: [/\bwon\b/i, /winner/i, /congratulat/i, /\bpromo(tion)?\b/i, /\bprize\b/i,
         /lucky (winner|customer)/i, /you (have|'ve)? ?been selected/i, /claim your/i, /bonanza/i],
    flag: { en: 'It says you won a prize or promo.',
            pcm: 'E talk say you win prize or promo.' },
    advice: { en: 'If you did not enter, you did not win. Real prizes never need a fee or your PIN. Verify only via the official channel.',
              pcm: 'If you no enter, you no win. Real prize no dey need fee or your PIN. Verify only for official channel.' },
  },
  {
    id: 'fee', cat: 'fee', weight: 4,
    re: [/processing fee/i, /activation fee/i, /delivery fee/i, /clearance/i,
         /pay\b.{0,30}\b(to|before|first|and)\b.{0,20}(receive|claim|unlock|process|collect|get)/i,
         /small (fee|amount|token)/i, /registration fee/i],
    flag: { en: 'It asks you to pay a fee first.',
            pcm: 'E ask make you pay fee first.' },
    advice: { en: 'You should never pay to receive a prize, job, loan, or refund. Paying first is the scam.',
              pcm: 'You no suppose pay before you receive prize, job, loan, or refund. To pay first na the scam.' },
  },
  {
    id: 'block-verify', cat: 'agent', weight: 3,
    re: [/block(ed|ing)?/i, /deactivat/i, /suspend/i, /expir(e|ing|ed)/i,
         /verify your (account|number|sim|wallet|details)/i, /update your (account|details|sim|info)/i,
         /reactivat/i, /(sim|account|number|line) will be (block|deactivat|suspend|clos)/i,
         /re-?register/i],
    flag: { en: 'It threatens that your account/SIM will be blocked unless you act.',
            pcm: 'E threaten say dem go block your account/SIM if you no act.' },
    advice: { en: 'This fear is manufactured to rush you. Your network warns you through official menus, not panic texts. Verify by calling them yourself.',
              pcm: 'Dis fear na to rush you. Your network dey warn you through official menu, no be panic text. Verify by calling dem yourself.' },
  },
  {
    id: 'impersonate', cat: 'agent', weight: 2,
    re: [/customer (care|service)/i, /\bmtn\b/i, /telecel/i, /airteltigo/i, /vodafone/i,
         /momo (team|care|support|office)/i, /head office/i, /\bagent\b/i, /official/i],
    flag: { en: 'It claims to be from your network or “customer care”.',
            pcm: 'E claim say na from your network or “customer care”.' },
    advice: { en: 'Anyone can claim this. Do not trust the caller ID or name — call the number on your SIM pack to verify.',
              pcm: 'Anybody fit claim am. No trust the caller ID or name — call the number for your SIM pack to verify.' },
  },
  {
    id: 'ghana-card', cat: 'simswap', weight: 4,
    re: [/ghana ?card/i, /national (id|identity)/i, /\bid number\b/i, /ghana-?card number/i,
         /date of birth/i],
    flag: { en: 'It asks for your Ghana Card or ID details.',
            pcm: 'E ask your Ghana Card or ID details.' },
    advice: { en: 'These details are used to swap your SIM and hijack your MoMo. Never give them to an incoming caller.',
              pcm: 'Dem dey use dis details swap your SIM and hijack your MoMo. No give am to person wey call you.' },
  },
  {
    id: 'urgency', cat: null, weight: 2,
    re: [/urgent/i, /immediately/i, /right now/i, /within \d+\s*(min|hour|hr)/i,
         /last chance/i, /hurry/i, /\basap\b/i, /act now/i, /quickly/i, /don'?t (tell|delay)/i],
    flag: { en: 'It pressures you to act urgently.',
            pcm: 'E dey pressure you make you act urgent.' },
    advice: { en: 'Urgency is a tool to stop you thinking. Slow down and verify — real matters can wait a few minutes.',
              pcm: 'Urgency na tool to stop you from think. Cool down and verify — real matter fit wait small.' },
  },
  {
    id: 'link', cat: null, weight: 3,
    re: [/bit\.ly/i, /tinyurl/i, /wa\.me/i, /\.(xyz|top|click|link|info)\b/i,
         /https?:\/\/(?!(www\.)?(csa\.gov\.gh|bog\.gov\.gh|mtn\.|telecel\.|airteltigo\.))/i],
    flag: { en: 'It contains a link, often a shortened or odd one.',
            pcm: 'E get link, e fit be shortened or strange one.' },
    advice: { en: 'Do not tap links in unexpected messages. They can steal your details. Type official addresses yourself.',
              pcm: 'No tap link for message wey you no expect. E fit thief your details. Type official address yourself.' },
  },
];

const VERDICTS = {
  danger: {
    level: 'danger',
    title: { en: 'Danger — this looks like a scam', pcm: 'Danger — dis be like scam' },
    line: { en: 'Do not share anything, pay, or dial any code. Stop and verify.',
            pcm: 'No share anything, no pay, no dial any code. Stop and verify.' },
  },
  caution: {
    level: 'caution',
    title: { en: 'Be careful — several warning signs', pcm: 'Be careful — plenty warning signs dey' },
    line: { en: 'Treat this as suspicious. Verify through official channels before you act.',
            pcm: 'Take am as suspicious. Verify through official channel before you act.' },
  },
  clear: {
    level: 'clear',
    title: { en: 'No obvious scam signs found', pcm: 'No obvious scam signs dey' },
    line: { en: 'This does not mean it is safe. Never share your PIN/OTP, and verify anything about money.',
            pcm: 'Dis no mean say e safe. No share your PIN/OTP, and verify anything about money.' },
  },
};

/* Analyze pasted text -> verdict + the exact red flags matched. */
function analyzeText(text) {
  const hits = [];
  let score = 0, critical = false;
  const cats = new Set();
  for (const rule of RULES_DETECT) {
    if (rule.re.some((re) => re.test(text))) {
      hits.push({ id: rule.id, cat: rule.cat, flag: rule.flag, advice: rule.advice });
      score += rule.weight;
      if (rule.critical) critical = true;
      if (rule.cat) cats.add(rule.cat);
    }
  }
  let verdict = VERDICTS.clear;
  if (critical || score >= 6) verdict = VERDICTS.danger;
  else if (score >= 3) verdict = VERDICTS.caution;
  return { verdict, score, hits, scams: [...cats] };
}

/* Normalise a Ghanaian phone number for comparison. */
function normNumber(raw) {
  let n = (raw || '').replace(/[^\d+]/g, '');
  n = n.replace(/^\+?233/, '0');           // +233xxxxxxxxxx -> 0xxxxxxxxxx
  if (n.length === 9 && !n.startsWith('0')) n = '0' + n;
  return n;
}

window.SikaDetector = { analyzeText, normNumber, RULES_DETECT, VERDICTS };
})();
