import { workflow, node, trigger, sticky, ifElse, expr } from '@n8n/workflow-sdk';

const TABLE = { __rl: true, mode: 'id', value: 'xxdPIIe3xCVSZR44', cachedResultName: 'fariz_queue' };

const PARSE = `const fix = (t) => { let o = '', q = false, e = false; for (const c of t) { if (q) { if (e) { o += c; e = false; continue; } if (c === '\\\\') { o += c; e = true; continue; } if (c === '"') { q = false; o += c; continue; } if (c === '\\n') { o += '\\\\n'; continue; } if (c === '\\r' || c === '\\t') { o += ' '; continue; } o += c; } else { if (c === '"') q = true; o += c; } } return o; };
const txt = (j) => { const p = (j.content && j.content.parts) || j.parts; if (Array.isArray(p)) return p.map(x => typeof x.text === 'string' ? x.text : '').join(''); return typeof j.text === 'string' ? j.text : JSON.stringify(j); };
const extract = (j) => { const t = txt(j); const s = t.indexOf('{'), e = t.lastIndexOf('}'); if (s < 0 || e < 0) throw new Error('no JSON'); const b = t.slice(s, e + 1); try { return JSON.parse(b); } catch (x) { return JSON.parse(fix(b)); } };
const ok = (d, type) => { if (!d || !d.title || !Array.isArray(d.sources) || d.sources.filter(x => x && /^https?:/.test(x.url || '')).length < 2) return 'missing title/sources'; if (type === 'reel') return (d.reel && Array.isArray(d.reel.scenes) && d.reel.scenes.length >= 5 && d.reel.cover) ? '' : 'reel incomplete'; return (Array.isArray(d.slides) && d.slides.length >= (type === 'carousel' ? 4 : 1)) ? '' : 'slides missing'; };`;

const daily = trigger({
  type: 'n8n-nodes-base.scheduleTrigger', version: 1.2,
  config: { name: 'كل يوم 3 عصرًا', parameters: { rule: { interval: [{ field: 'days', daysInterval: 1, triggerAtHour: 15, triggerAtMinute: 7 }] } } }
});

const getAll = node({
  type: 'n8n-nodes-base.dataTable', version: 1.1,
  config: { name: 'جلب سجل المحتوى', parameters: { resource: 'row', operation: 'get', dataTableId: TABLE, returnAll: true, orderBy: true, orderByColumn: 'post_number', orderByDirection: 'ASC' } }
});

const pick = node({
  type: 'n8n-nodes-base.code', version: 2,
  config: { name: 'اختيار الموضوع التالي', parameters: { mode: 'runOnceForAllItems', language: 'javaScript', jsCode: `const rows = $input.all().map(i => i.json).filter(r => r.post_number);
const READY = ['APPROVED', 'DESIGNING', 'READY_FOR_REVIEW', 'SCHEDULED'];
const stock = rows.filter(r => READY.includes(r.status)).length;
// مخزون احتياطي: لا تنتج إذا كان هناك 4 منشورات جاهزة أو أكثر
if (stock >= 4) return [];
const PHASE_NAME = { syria: 'سوريا — البداية', arab: 'العالم العربي — من سوريا إلى المحيط', world: 'من العالم إلى الفكرة', continuous: 'الإنتاج المستمر' };
const prev = rows.map(r => r.title || r.topic).filter(Boolean);
const idea = rows.find(r => r.status === 'IDEA');
const TYPES = ['reel', 'static', 'carousel', 'static', 'reel', 'carousel', 'interactive'];
let job;
if (idea) {
  job = { mode: 'plan', row_id: idea.id, post_number: idea.post_number, topic: idea.topic, content_type: idea.content_type || TYPES[idea.post_number % 7], phase: idea.phase || 'syria' };
} else {
  const n = Math.max(90, ...rows.map(r => r.post_number)) + 1;
  job = { mode: 'discover', row_id: null, post_number: n, topic: '', content_type: TYPES[n % 7], phase: 'continuous' };
}
job.phase_name = PHASE_NAME[job.phase] || job.phase;
job.previous = prev.slice(-150).join(' | ');
return [{ json: job }];` } }
});

const SCHEMA = `{"title":"عنوان قصير","topic":"الموضوع","slides":[{"layout":"cover|points|text|list|quiz|close","headline":"عنوان أبيض قصير","headline_gold":"عنوان ذهبي (اختياري)","sub":"سطر فرعي","label":"تسمية في إطار","icon":"اسم أيقونة","text":"فقرة (يمكن تمييز كلمات بـ **نجمتين**)","stat":"رقم بارز","stat_label":"شرح الرقم","points":[{"icon":"...","title":"...","text":"..."}],"rows":[{"k":"سنة/مفتاح قصير","v":"الحدث","note":"ملاحظة"}],"options":["أ","ب","ج","د"],"quote":"جملة ختامية من صياغتك","note":"سطر أخير","bg":"English background image prompt"}],"reel":{"cover":{"headline":"...","headline_gold":"...","sub":"...","bg":"English prompt"},"scenes":[{"voice":"جملة تعليق صوتي بالفصحى","caption":"نص قصير على الشاشة","gold":["كلمة من الكابشن تُلوَّن"],"bg":"English prompt"}]},"caption":"كابشن إنستغرام","hashtags":"#... #...","sources":[{"title":"...","url":"https://..."}]}`;

const write = node({
  type: '@n8n/n8n-nodes-langchain.googleGemini', version: 1.2,
  config: {
    name: 'كتابة المنشور (Gemini + بحث)', retryOnFail: true, maxTries: 3, waitBetweenTries: 5000,
    parameters: {
      resource: 'text', operation: 'message', modelId: { __rl: true, mode: 'id', value: 'models/gemini-2.5-flash' },
      messages: { values: [{ role: 'user', content: expr(`أنت فريق تحرير علامة FARIZ KANAAN المعرفية على إنستغرام (باحث | كاتب | مفكر). الشعار: «من سوريا… تبدأ الحكاية، ومن العالم… تتسع الرؤية». النبرة: رصينة، تحليلية، عميقة، غير مبتذلة، بلا مبالغة ولا عناوين مضللة.

رقم المنشور: {{ $json.post_number }}
المرحلة التحريرية: {{ $json.phase_name }}
نوع المحتوى المطلوب: {{ $json.content_type }}
{{ $json.mode === 'plan' ? 'الموضوع المحدد في الخطة: ' + $json.topic : 'لا يوجد موضوع محدد: ابحث بنفسك (Google Search) عن موضوع معرفي جديد عالي القيمة في التاريخ أو الحضارات أو الفكر أو العلوم أو السياسة الدولية أو المجتمع أو الأدب، عربي أو عالمي، دائم القيمة أو مرتبط بذكرى/حدث حالي، ويناسب جمهورًا عربيًا وعالميًا.' }}

المواضيع السابقة (ممنوع تكرارها أو تقديمها بصياغة أخرى): {{ $json.previous }}

الخطوة 1: ابحث في Google عن الموضوع من مصادر موثوقة (موسوعات كبريتانيكا، اليونسكو، جامعات، مؤسسات رسمية، دراسات). تحقق من كل اسم وتاريخ ورقم. إذا اختلفت الروايات فاذكر ذلك صراحة. لا تخترع أي معلومة أو اقتباس.
الخطوة 2: اكتب المحتوى بالعربية الفصحى السليمة (همزات وتاء مربوطة صحيحة)، نص مختصر وقوي داخل التصميم.

قواعد حسب النوع:
- static: شريحة واحدة فقط. اختر layout من: points (4 أو 6 نقاط، كل نقطة: icon و title حتى 3 كلمات و text حتى 10 كلمات) أو text (فقرة حتى 45 كلمة، يمكن إضافة stat و stat_label و icon) أو list (3 إلى 5 صفوف: k قصير جدًا مثل سنة، v حتى 7 كلمات، note اختيارية).
- carousel: من 5 إلى 6 شرائح: الأولى layout=cover (headline كلمة أو كلمتان، headline_gold، sub سؤال جذاب، label="كاروسيل | اسحب للقراءة")، ثم شرائح text/points/list كل واحدة تضيف معلومة جديدة متصلة بما قبلها، والأخيرة layout=close (headline + quote جملة تأملية من صياغتك + sub دعوة للمتابعة).
- interactive: شريحة واحدة layout=quiz (label="اختبر معلوماتك"، headline + headline_gold سؤال، options 4 خيارات قصيرة، sub="اكتب الحرف في التعليقات") واجعل الإجابة الصحيحة في آخر الكابشن بعد عدة أسطر من النقاط.
- reel: املأ reel فقط (بدون slides): cover (headline كلمة أو كلمتان، headline_gold حتى 4 كلمات، sub سطر)، و6 إلى 8 مشاهد. voice جملة تعليق صوتي بالفصحى حتى 25 كلمة، اكتب الأعداد والسنوات بالحروف داخل voice. caption حتى 5 كلمات (يمكن فيه أرقام). المشهد الأول افتتاحية قوية جدًا تشد خلال ثانيتين. المجموع 35 إلى 60 ثانية.
- الأيقونات المتاحة فقط: anchor, book-open, brain, building, calendar, castle, church, circle-help, coins, columns, compass, crown, droplets, feather, file-text, flame, gem, globe, history, hourglass, landmark, languages, library, lightbulb, map-pinned, map, mic, milestone, mountain, network, pen-tool, quote, route, scale, scroll-text, scroll, search, shield, ship, sprout, star, sun, tablet, tent, trees, users, waves, wheat.
- bg لكل شريحة/مشهد: وصف إنجليزي لصورة خلفية سينمائية داكنة تاريخية تناسب اللحظة، بلا أشخاص معروفين، بلا نصوص، العناصر على الأطراف والوسط فارغ.
- headline حتى 4 كلمات، headline_gold حتى 6 كلمات.
- caption: 3 إلى 6 أسطر: افتتاحية تشد، خلاصة معرفية، ثم سؤال للنقاش أو دعوة للحفظ/المشاركة. بلا هاشتاقات داخل الكابشن.
- hashtags: من 7 إلى 10 هاشتاقات عربية وإنجليزية دقيقة، وآخرها #FarizKanaan.
- sources: من 2 إلى 4 مصادر حقيقية بروابط تعمل فعلًا راجعتها في البحث.

أعد كائن JSON واحدًا فقط بلا أي نص آخر، بهذه المفاتيح (احذف ما لا يلزم النوع):
${SCHEMA}`) }] },
      simplify: true, jsonOutput: false,
      options: { maxOutputTokens: 8192, temperature: 0.7, thinkingBudget: 2048 },
      builtInTools: { googleSearch: true }
    }
  }
});

const check = node({
  type: '@n8n/n8n-nodes-langchain.googleGemini', version: 1.2,
  config: {
    name: 'تدقيق الحقائق (Gemini + بحث)', retryOnFail: true, maxTries: 3, waitBetweenTries: 5000,
    parameters: {
      resource: 'text', operation: 'message', modelId: { __rl: true, mode: 'id', value: 'models/gemini-2.5-flash' },
      messages: { values: [{ role: 'user', content: expr(`أنت مدقق حقائق ومحرر لغوي صارم لعلامة معرفية لا تنشر أي معلومة غير موثقة.
استخدم Google Search للتحقق من كل ادعاء في هذه المسودة: الأسماء والتواريخ والأرقام والأماكن والعلاقات السببية والاقتباسات، وتحقق أن روابط المصادر حقيقية وتدعم المحتوى.
نوع المحتوى: {{ $('اختيار الموضوع التالي').item.json.content_type }}
المسودة (رد الكاتب، JSON بداخله): {{ JSON.stringify($json) }}

القرار:
- إذا كان جوهر الموضوع خاطئًا أو غير قابل للتحقق، أو المصادر ضعيفة/مختلقة: أعد {"verdict":"reject","reason":"..."}.
- وإلا: صحح كل خطأ، واحذف كل تفصيل لا يمكن التحقق منه، ووضّح الروايات المختلف عليها، وصحح الإملاء العربي (الهمزات، التاء المربوطة، الألف المقصورة)، واحذف أي اقتباس غير موثق، واستبدل أي مصدر غير صالح بمصدر حقيقي. حافظ على البنية والمفاتيح والطول والأسلوب كما هي.

أعد JSON واحدًا فقط: {"verdict":"ok","content":{...المسودة المصححة بنفس المفاتيح...},"notes":"ما الذي صححته"} أو كائن الرفض.`) }] },
      simplify: true, jsonOutput: false,
      options: { maxOutputTokens: 8192, temperature: 0.1, thinkingBudget: 2048 },
      builtInTools: { googleSearch: true }
    }
  }
});

const approve = node({
  type: 'n8n-nodes-base.code', version: 2,
  config: { name: 'اعتماد الموثّق فقط', parameters: { mode: 'runOnceForEachItem', language: 'javaScript', jsCode: PARSE + `
const job = $('اختيار الموضوع التالي').item.json;
let status = 'APPROVED', notes = '', d = null;
try { const r = extract($json); if (r.verdict !== 'ok') { status = 'NEEDS_CORRECTION'; notes = 'رفض المدقق: ' + String(r.reason || '').slice(0, 500); } else { d = r.content; const bad = ok(d, job.content_type); if (bad) { status = 'NEEDS_CORRECTION'; notes = bad; } else notes = String(r.notes || '').slice(0, 900); } } catch (e) { status = 'NEEDS_CORRECTION'; notes = 'فشل التدقيق: ' + String(e.message).slice(0, 300); }
d = d || { title: job.topic || 'بدون عنوان' };
const full = Object.assign({}, d, { post_number: job.post_number, type: job.content_type, lang: 'ar', phase: job.phase });
return { json: { row_id: job.row_id, post_number: job.post_number, content_type: job.content_type, phase: job.phase, lang: 'ar', topic: String(d.topic || job.topic || '').slice(0, 200), title: String(d.title).slice(0, 150), caption: String(d.caption || ''), hashtags: String(d.hashtags || ''), sources: JSON.stringify(d.sources || []), content: JSON.stringify(full), status, verify_notes: notes } };` } }
});

const COLS = ['post_number', 'content_type', 'lang', 'phase', 'topic', 'title', 'content', 'caption', 'hashtags', 'sources', 'status', 'verify_notes'];
const schema = COLS.map(c => ({ id: c, displayName: c, type: c === 'post_number' ? 'number' : 'string', display: true }));
const mapping = Object.fromEntries(COLS.map(c => [c, expr('{{ $json.' + c + ' }}')]));

const isNew = ifElse({
  version: 2.2,
  config: { name: 'موضوع جديد خارج الخطة؟', parameters: { conditions: { options: { caseSensitive: true, leftValue: '', typeValidation: 'loose' }, conditions: [{ leftValue: expr('{{ $json.row_id ? "" : "new" }}'), operator: { type: 'string', operation: 'equals' }, rightValue: 'new' }], combinator: 'and' } } }
});

const insertRow = node({
  type: 'n8n-nodes-base.dataTable', version: 1.1,
  config: { name: 'إضافة منشور جديد للسجل', parameters: { resource: 'row', operation: 'insert', dataTableId: TABLE, columns: { mappingMode: 'defineBelow', value: mapping, schema } } }
});

const updateRow = node({
  type: 'n8n-nodes-base.dataTable', version: 1.1,
  config: { name: 'تحديث المنشور في السجل', parameters: { resource: 'row', operation: 'update', dataTableId: TABLE, matchType: 'allConditions', filters: { conditions: [{ keyName: 'id', condition: 'eq', keyValue: expr('{{ $json.row_id }}') }] }, columns: { mappingMode: 'defineBelow', value: mapping, schema } } }
});

const note = sticky('## FARIZ KANAAN — إنتاج المحتوى\nكل يوم 3 عصرًا: إذا قلّ المخزون الجاهز عن 4 منشورات، يأخذ أول موضوع IDEA من خطة 11–90، يكتبه Gemini بالبحث ثم يدقّقه مدقق ثانٍ. الموثّق فقط يصبح APPROVED، والمرفوض NEEDS_CORRECTION ولا يُنشر.\nبعد المنشور 90 يكتشف موضوعات جديدة بنفسه (91، 92، …) بلا نهاية.', [], { color: 4, width: 620, height: 220 });

export default workflow('fariz-generate', 'FARIZ KANAAN - إنتاج المحتوى اليومي')
  .add(note)
  .add(daily)
  .to(getAll)
  .to(pick)
  .to(write)
  .to(check)
  .to(approve)
  .to(isNew.onTrue(insertRow).onFalse(updateRow));
