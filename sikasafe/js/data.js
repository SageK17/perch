/* ============================================================
   SikaSafe — data & content
   "sika/shika" = money (Akan/Gã). Guard your MoMo money.

   100% offline. No account, no tracking. Nothing you type ever
   leaves your phone. Content grounded in Ghana Cyber Security
   Authority (CSA) guidance and reporting on Ghanaian MoMo fraud.

   Translations: English and Ghanaian Pidgin are complete. Gã is a
   community DRAFT — it should be checked by a native Gã speaker
   before people rely on it. Strings with no Gã fall back to English.
   ============================================================ */
(function () {
'use strict';

/* ---------- Languages ---------- */
const LOCALES = [
  { code: 'en',  label: 'English',  draft: false },
  { code: 'pcm', label: 'Pidgin',   draft: false },
  { code: 'gaa', label: 'Gã',       draft: true  },
];

/* Pick a string for the active locale, falling back to English. */
function t(obj) {
  if (obj == null) return '';
  if (typeof obj === 'string') return obj;
  const loc = window.SikaState ? window.SikaState.locale : 'en';
  return obj[loc] || obj.en || '';
}

/* ---------- UI strings ---------- */
const UI = {
  appName: 'SikaSafe',
  tagline: {
    en: 'Guard your MoMo. Spot the scam before it takes your money.',
    pcm: 'Guard your MoMo. Catch the scam before e chop your money.',
    gaa: 'Bu oshika. Na julɔ dani ehe oshika.', // draft
  },
  nav: {
    check:  { en: 'Check',   pcm: 'Check',   gaa: 'Kwɛmɔ' },   // draft
    learn:  { en: 'Learn',   pcm: 'Learn',   gaa: 'Kasemɔ' },  // draft
    report: { en: 'Reports', pcm: 'Reports', gaa: 'Reports' },
    help:   { en: 'Help',    pcm: 'Help',    gaa: 'Yelikɛbuamɔ' }, // draft
  },
  checkTitle: {
    en: 'Is this a scam?',
    pcm: 'Na scam be dis?',
    gaa: 'Julɔ nii nɛɛ lo?', // draft
  },
  checkSub: {
    en: 'Paste a text message, or pick what is happening. We check it right here on your phone.',
    pcm: 'Paste the message, or pick wetin dey happen. We go check am here for your phone.',
  },
  pastePlaceholder: {
    en: 'Paste the SMS or WhatsApp message here…',
    pcm: 'Paste the SMS or WhatsApp message here…',
  },
  analyze: { en: 'Check it', pcm: 'Check am', gaa: 'Kwɛmɔ' },
  orPick: { en: 'or pick what is happening', pcm: 'or pick wetin dey happen' },
  clear: { en: 'Clear', pcm: 'Clear' },
  golden: {
    en: 'The 7 golden rules',
    pcm: 'The 7 golden rules',
    gaa: 'Mlaa 7 lɛ', // draft
  },
  shareRules: { en: 'Share these rules', pcm: 'Share these rules' },
  reportTitle: {
    en: 'Community scam reports',
    pcm: 'Community scam reports',
  },
  reportSub: {
    en: 'Warn others about a scam number. Reports stay on your phone (sharing to a common list needs a server — see the README).',
    pcm: 'Warn others about a scam number. Reports dey stay for your phone (to share one common list need server — check README).',
  },
  lookupPlaceholder: { en: 'Enter a phone number to look up…', pcm: 'Enter phone number make you check…' },
  lookup: { en: 'Look up', pcm: 'Check am' },
  reportNumber: { en: 'Report a scam number', pcm: 'Report scam number' },
  helpTitle: {
    en: 'Scammed? Do this now',
    pcm: 'Dem scam you? Do dis now',
  },
  disclaimer: {
    en: 'SikaSafe gives guidance only — it cannot see your MoMo account and “not reported” does not mean “safe”. When unsure, call your network or CSA on 292.',
    pcm: 'SikaSafe dey give advice only — e no fit see your MoMo account, and “dem never report am” no mean say e safe. If you no sure, call your network or CSA for 292.',
  },
  gaDraftNote: {
    en: 'Gã here is an early community draft. Please help us get it right.',
    pcm: 'This Gã na early community draft. Abeg help us make e correct.',
    gaa: 'Gã nɛɛ ji community draft. Ofainɛ ye bua wɔ.', // draft
  },
};

/* ---------- The golden rules (the heart of the app) ---------- */
const RULES = [
  {
    icon: 'lock',
    title: { en: 'Your PIN is a secret — forever',
             pcm: 'Your PIN na secret — forever',
             gaa: 'O PIN lɛ ji teemɔ nii' }, // draft
    body: { en: 'MoMo, your network, banks, the police — NONE of them will ever ask for your PIN or the code (OTP) they send you. Anyone who asks is a thief.',
            pcm: 'MoMo, your network, bank, police — NONE of dem go ever ask your PIN or the code (OTP) wey dem send you. Anybody wey ask, na thief.' },
  },
  {
    icon: 'download',
    title: { en: 'To RECEIVE money you need nothing',
             pcm: 'To RECEIVE money you no need anything' },
    body: { en: 'You never enter a PIN or dial a code to receive money. If a message says “enter your PIN / dial this to receive”, it is a scam.',
            pcm: 'You no dey enter PIN or dial code before money enter. If message talk say “enter your PIN / dial dis to receive”, na scam.' },
  },
  {
    icon: 'balance',
    title: { en: 'Trust your balance, not an SMS',
             pcm: 'Trust your balance, no be SMS' },
    body: { en: 'Alert messages can be faked. Before you act on “you have received…”, check your REAL balance from your own network’s MoMo menu.',
            pcm: 'Dem fit fake alert message. Before you do anything on top “you don receive…”, check your REAL balance for your own network MoMo menu.' },
  },
  {
    icon: 'reverse',
    title: { en: 'A “wrong transfer” is a trap',
             pcm: 'A “wrong transfer” na trap' },
    body: { en: 'If a stranger begs you to “send back” money they say they sent by mistake, stop. Check your real balance first — the credit is usually fake.',
            pcm: 'If stranger dey beg you “send back” money wey dem talk say dem send by mistake, stop. Check your real balance first — the credit dey mostly fake.' },
  },
  {
    icon: 'dial',
    title: { en: 'Never dial codes a stranger gives you',
             pcm: 'No dial code wey stranger give you' },
    body: { en: 'Some USSD codes secretly approve a payment or move your airtime and money. Only dial codes you started yourself.',
            pcm: 'Some USSD code fit secretly approve payment or move your airtime and money. Only dial code wey you yourself start.' },
  },
  {
    icon: 'clock',
    title: { en: 'Slow down — pressure is the trick',
             pcm: 'Cool down — pressure na the trick' },
    body: { en: 'Scammers rush you: “now! urgent! last chance!”. Real business can wait five minutes for you to verify.',
            pcm: 'Scammers dey rush you: “now! urgent! last chance!”. Real business fit wait five minutes make you verify.' },
  },
  {
    icon: 'signal',
    title: { en: 'Lost signal for no reason? Act fast',
             pcm: 'Your line lost signal for no reason? Move fast' },
    body: { en: 'If your SIM suddenly has no service, someone may be swapping your line to steal your MoMo. Call your network immediately from another phone.',
            pcm: 'If your SIM sharp-sharp no get service, person fit dey swap your line to thief your MoMo. Call your network sharp-sharp from another phone.' },
  },
];

/* ---------- Scam types (Learn) ---------- */
const SCAMS = [
  {
    id: 'reverse',
    icon: 'reverse',
    name: { en: '“I sent it by mistake — send it back”', pcm: '“I send am by mistake — send am back”' },
    how: { en: 'You get a fake “You have received GHS ___” message. Then someone calls, sounding stressed, saying they sent it to you by error and begging you to send it back. The credit was never real — but the money you send is.',
           pcm: 'You go get fake “You don receive GHS ___” message. Then person go call, dey sound stressed, talk say dem send am give you by mistake and dey beg make you send am back. The credit no be real — but the money wey you send, e real.' },
    signs: {
      en: ['An SMS “credit” you did not expect', 'A caller who is stressed and rushing you', 'They beg you to send it back quickly', 'They do not want you to check your balance first'],
      pcm: ['SMS “credit” wey you no expect', 'Person wey dey stressed and dey rush you', 'Dem dey beg make you send am back quick-quick', 'Dem no want make you check your balance first'],
    },
    protect: {
      en: ['Check your REAL balance from the MoMo menu before anything', 'If the money is not truly there, it is a scam — send nothing', 'Tell the caller you will let MoMo reverse any true error', 'Block and report the number'],
      pcm: ['Check your REAL balance for MoMo menu before anything', 'If the money no dey there for real, na scam — no send anything', 'Tell the caller say make MoMo reverse any true mistake', 'Block and report the number'],
    },
  },
  {
    id: 'agent',
    icon: 'headset',
    name: { en: 'Fake customer care / fake agent', pcm: 'Fake customer care / fake agent' },
    how: { en: 'Someone calls or texts claiming to be from MTN, Telecel, AirtelTigo or “MoMo customer care”. They say there is a problem with your wallet or SIM and ask you to confirm your PIN or an OTP, or to dial a code, to “fix” or “verify” it.',
           pcm: 'Person go call or text talk say na from MTN, Telecel, AirtelTigo or “MoMo customer care”. Dem go talk say problem dey your wallet or SIM and ask make you confirm your PIN or OTP, or dial code, to “fix” or “verify” am.' },
    signs: {
      en: ['They already “know” your name or number (this is easy to get)', 'They ask for your PIN, OTP, or Ghana Card details', 'They tell you to dial a code to “verify”', 'They threaten your account will be blocked'],
      pcm: ['Dem already “know” your name or number (e easy to get)', 'Dem ask your PIN, OTP, or Ghana Card details', 'Dem tell you make you dial code to “verify”', 'Dem threaten say dem go block your account'],
    },
    protect: {
      en: ['Real staff never ask for your PIN or OTP — hang up', 'Do not dial any code they give you', 'Call the network yourself on the number on your SIM pack', 'Never confirm Ghana Card or personal details to an incoming caller'],
      pcm: ['Real staff no dey ask your PIN or OTP — hang up', 'No dial any code wey dem give you', 'Call the network yourself for the number wey dey your SIM pack', 'No confirm Ghana Card or personal details to person wey call you'],
    },
  },
  {
    id: 'promo',
    icon: 'gift',
    name: { en: '“You have won!” promo / prize', pcm: '“You don win!” promo / prize' },
    how: { en: 'A message or call says you won a promo (cash, a car, airtime). To “claim” it you must dial a code, share an OTP, or pay a small “processing fee”. There is no prize.',
           pcm: 'Message or call talk say you don win promo (cash, car, airtime). Before you “claim” am you must dial code, share OTP, or pay small “processing fee”. No prize dey.' },
    signs: {
      en: ['You did not enter any promo', 'You must pay a fee to receive a prize', 'You must dial a code or share an OTP to “claim”', 'Big reward, big rush'],
      pcm: ['You no enter any promo', 'You must pay fee before you receive prize', 'You must dial code or share OTP to “claim”', 'Big reward, big rush'],
    },
    protect: {
      en: ['Real prizes never need a fee or your PIN/OTP', 'Verify any promo only through the network’s official channel', 'Do not dial the code — delete the message'],
      pcm: ['Real prize no dey need fee or your PIN/OTP', 'Verify any promo only through the network official channel', 'No dial the code — delete the message'],
    },
  },
  {
    id: 'code',
    icon: 'dial',
    name: { en: 'The “dial this code” trick', pcm: 'The “dial dis code” trick' },
    how: { en: 'A caller gives you a USSD code to dial — claiming it will register you, confirm a delivery, or unlock a reward. The code actually authorises a payment, airtime transfer, or money transfer to them.',
           pcm: 'Person go give you USSD code make you dial — talk say e go register you, confirm delivery, or unlock reward. The code actually dey authorise payment, airtime transfer, or money transfer give dem.' },
    signs: {
      en: ['A stranger tells you exactly what code to dial', 'The code starts with * and ends with #', 'They stay on the line while you dial', 'You are told it is “just to confirm”'],
      pcm: ['Stranger dey tell you the exact code to dial', 'The code start with * and end with #', 'Dem dey stay for line while you dey dial', 'Dem tell you say e be “just to confirm”'],
    },
    protect: {
      en: ['Never dial a code someone else gives you', 'Hang up and dial your own network’s official MoMo menu yourself', 'If you already dialled, change your PIN and call your network now'],
      pcm: ['No dial code wey another person give you', 'Hang up and dial your own network official MoMo menu yourself', 'If you don already dial am, change your PIN and call your network now'],
    },
  },
  {
    id: 'simswap',
    icon: 'signal',
    name: { en: 'SIM-swap takeover', pcm: 'SIM-swap takeover' },
    how: { en: 'A fraudster uses a forged Ghana Card to get a replacement SIM for your number. Your phone loses service; theirs now receives your calls, SMS and OTPs — and they drain your MoMo.',
           pcm: 'Fraudster go use fake Ghana Card get replacement SIM for your number. Your phone go lose service; dem own go dey receive your calls, SMS and OTPs — and dem go drain your MoMo.' },
    signs: {
      en: ['Your SIM suddenly shows “No service” for no reason', 'You stop getting calls and SMS', 'You cannot access MoMo', 'It often follows calls fishing for your details'],
      pcm: ['Your SIM sharp-sharp show “No service” for no reason', 'You stop to dey get calls and SMS', 'You no fit access MoMo', 'E dey often follow calls wey dey fish your details'],
    },
    protect: {
      en: ['If your line goes dead unexpectedly, call your network at once from another phone', 'Ask them to freeze your line and MoMo', 'Set a SIM PIN and a strong, separate MoMo PIN', 'Never share Ghana Card details with callers'],
      pcm: ['If your line die anyhow, call your network sharp-sharp from another phone', 'Tell dem make dem freeze your line and MoMo', 'Set SIM PIN and strong, separate MoMo PIN', 'No share Ghana Card details with people wey call you'],
    },
  },
  {
    id: 'fee',
    icon: 'gift',
    name: { en: 'Pay-a-fee-first (job, loan, goods)', pcm: 'Pay-fee-first (job, loan, goods)' },
    how: { en: 'A “job offer”, “loan approval”, or a great item for sale asks you to first send a small fee by MoMo — for processing, forms, or delivery. Once you pay, they vanish.',
           pcm: 'A “job offer”, “loan approval”, or fine item wey dem dey sell ask make you first send small fee by MoMo — for processing, forms, or delivery. Once you pay, dem disappear.' },
    signs: {
      en: ['You must pay before you receive anything', 'Deal is too good — cheap item, easy job, fast loan', 'Payment must be by MoMo to a personal number', 'Pressure to “pay now to secure it”'],
      pcm: ['You must pay before you receive anything', 'The deal too sweet — cheap item, easy job, fast loan', 'Payment must be by MoMo to personal number', 'Pressure say “pay now to secure am”'],
    },
    protect: {
      en: ['Never pay a fee to receive a job, loan, or prize', 'For goods, meet in person or use trusted escrow / pay on delivery', 'Search the offer — scams are often reused word-for-word'],
      pcm: ['No pay fee to receive job, loan, or prize', 'For goods, meet person-to-person or use trusted escrow / pay on delivery', 'Search the offer — scam dey often reuse the same words'],
    },
  },
];

/* ---------- Quick situation picker (Check) ---------- */
const SITUATIONS = [
  { id: 'reverse', label: { en: 'Someone says they sent me money by mistake', pcm: 'Person talk say dem send me money by mistake' } },
  { id: 'agent',   label: { en: 'A caller asks for my PIN or a code (OTP)', pcm: 'Caller dey ask my PIN or code (OTP)' } },
  { id: 'promo',   label: { en: 'I got a message that I won a prize/promo', pcm: 'I get message say I win prize/promo' } },
  { id: 'code',    label: { en: 'Someone told me to dial a code', pcm: 'Person tell me make I dial code' } },
  { id: 'simswap', label: { en: 'My SIM suddenly has no signal', pcm: 'My SIM sharp-sharp no get signal' } },
  { id: 'fee',     label: { en: 'I must pay a fee first (job/loan/item)', pcm: 'I must pay fee first (job/loan/item)' } },
];

/* ---------- Official reporting contacts (verified) ---------- */
const CONTACTS = [
  { name: 'Cyber Security Authority (CSA)', primary: true,
    lines: [
      { label: 'Call or SMS', value: '292', tel: '292' },
      { label: 'WhatsApp', value: '0501603111', wa: '233501603111' },
      { label: 'Email', value: 'report@csa.gov.gh', mail: 'report@csa.gov.gh' },
    ],
    note: { en: 'Ghana’s 24/7 line to report any cyber fraud or check if a link/number is safe.',
            pcm: 'Ghana 24/7 line to report any cyber fraud or check if link/number safe.' } },
  { name: 'MTN', lines: [{ label: 'Customer care', value: '100', tel: '100' }],
    note: { en: 'Dial 100 from your MTN line to report and freeze MoMo.', pcm: 'Dial 100 from your MTN line to report and freeze MoMo.' } },
  { name: 'Telecel', lines: [{ label: 'Care line', value: '0501 000 000', tel: '0501000000' }],
    note: { en: 'Report and request a freeze on your wallet/line.', pcm: 'Report and ask make dem freeze your wallet/line.' } },
  { name: 'AirtelTigo', lines: [{ label: 'Care line', value: '0599 000 000', tel: '0599000000' }],
    note: { en: 'Report and request a freeze on your wallet/line.', pcm: 'Report and ask make dem freeze your wallet/line.' } },
  { name: 'Bank of Ghana — Consumer Protection',
    lines: [
      { label: 'Phone', value: '0302 686 401', tel: '0302686401' },
      { label: 'Email', value: 'consumerprotection@bog.gov.gh', mail: 'consumerprotection@bog.gov.gh' },
    ],
    note: { en: 'Escalate an unresolved MoMo/bank fraud complaint.', pcm: 'Escalate MoMo/bank fraud complaint wey dem no solve.' } },
];

/* ---------- "Scammed? Do this now" checklist ---------- */
const EMERGENCY = [
  { en: 'Act within minutes — speed matters most.', pcm: 'Move within minutes — speed matter pass everything.' },
  { en: 'Call your network now and ask them to FREEZE your MoMo wallet and line (MTN 100 · Telecel 0501 000 000 · AirtelTigo 0599 000 000).',
    pcm: 'Call your network now make dem FREEZE your MoMo wallet and line (MTN 100 · Telecel 0501 000 000 · AirtelTigo 0599 000 000).' },
  { en: 'If you shared your PIN, change it immediately from the MoMo menu (if you can still access it).',
    pcm: 'If you share your PIN, change am now-now for MoMo menu (if you fit still access am).' },
  { en: 'Report to the CSA: call/SMS 292 or WhatsApp 0501603111.', pcm: 'Report to CSA: call/SMS 292 or WhatsApp 0501603111.' },
  { en: 'File a police report (this helps any refund claim).', pcm: 'Go make police report (e go help any refund claim).' },
  { en: 'Escalate to Bank of Ghana Consumer Protection if it is not resolved: 0302 686 401.',
    pcm: 'Escalate go Bank of Ghana Consumer Protection if dem no solve am: 0302 686 401.' },
  { en: 'Warn family and friends — report the number in SikaSafe so others are alerted.',
    pcm: 'Warn family and friends — report the number for SikaSafe make others get alert.' },
];

window.SikaData = { LOCALES, UI, RULES, SCAMS, SITUATIONS, CONTACTS, EMERGENCY, t };
})();
