import { workflow, node, trigger, sticky, ifElse, expr, newCredential } from '@n8n/workflow-sdk';

const TABLE = { __rl: true, mode: 'id', value: 'xxdPIIe3xCVSZR44', cachedResultName: 'fariz_queue' };
const TOKEN = '1891f7bfe9498d518871e914ba10d0cb440938dc';
const IG = 'https://graph.instagram.com/v23.0/';
const COND = (left, op, right) => ({ options: { caseSensitive: true, leftValue: '', typeValidation: 'loose' }, conditions: [{ leftValue: left, operator: { type: 'string', operation: op }, rightValue: right }], combinator: 'and' });
const igCred = { httpQueryAuth: newCredential('Instagram FARIZ KANAAN (access_token)') };

// ------------- تسليم المنشور التالي لمحرك التصميم -------------
const nextHook = trigger({ type: 'n8n-nodes-base.webhook', version: 2.2, config: { name: 'طلب المنشور التالي', parameters: { httpMethod: 'GET', path: 'fariz-next', responseMode: 'responseNode' } } });
const tokenOk = ifElse({ version: 2.2, config: { name: 'المفتاح صحيح؟', parameters: { conditions: COND(expr('{{ $json.query?.token ?? "" }}'), 'equals', TOKEN) } } });
const getReady = node({ type: 'n8n-nodes-base.dataTable', version: 1.1, config: { name: 'جلب الجاهز للتصميم', alwaysOutputData: true, parameters: { resource: 'row', operation: 'get', dataTableId: TABLE, matchType: 'anyCondition', filters: { conditions: [{ keyName: 'status', condition: 'eq', keyValue: 'APPROVED' }, { keyName: 'status', condition: 'eq', keyValue: 'DESIGNING' }] }, returnAll: false, limit: 100, orderBy: true, orderByColumn: 'post_number', orderByDirection: 'ASC' } } });
const pickNext = node({ type: 'n8n-nodes-base.code', version: 2, config: { name: 'اختيار المنشور', parameters: { mode: 'runOnceForAllItems', language: 'javaScript', jsCode: `const rows = $input.all().map(i => i.json).filter(r => r.id);
const want = Number($('طلب المنشور التالي').first().json.query?.post || 0);
const old = Date.now() - 3 * 3600 * 1000;
let hit = want ? rows.find(r => r.post_number === want) : null;
hit = hit || rows.find(r => r.status === 'DESIGNING' && new Date(r.updatedAt).getTime() < old) || rows.find(r => r.status === 'APPROVED');
return [{ json: hit ? { found: 'yes', row_id: hit.id, post_number: hit.post_number, content: hit.content } : { found: 'no' } }];` } } });
const found = ifElse({ version: 2.2, config: { name: 'يوجد منشور؟', parameters: { conditions: COND(expr('{{ $json.found }}'), 'equals', 'yes') } } });
const markDesigning = node({ type: 'n8n-nodes-base.dataTable', version: 1.1, config: { name: 'تعليمه قيد التصميم', parameters: { resource: 'row', operation: 'update', dataTableId: TABLE, matchType: 'allConditions', filters: { conditions: [{ keyName: 'id', condition: 'eq', keyValue: expr('{{ $json.row_id }}') }] }, columns: { mappingMode: 'defineBelow', value: { status: 'DESIGNING' }, schema: [{ id: 'status', displayName: 'status', type: 'string', display: true }] } } } });
const sendPost = node({ type: 'n8n-nodes-base.respondToWebhook', version: 1.5, config: { name: 'إرسال المنشور', parameters: { respondWith: 'json', responseBody: expr('{{ JSON.stringify($("اختيار المنشور").first().json) }}') } } });
const none = node({ type: 'n8n-nodes-base.respondToWebhook', version: 1.5, config: { name: 'لا يوجد منشور جاهز', parameters: { respondWith: 'json', responseBody: '{"empty": true}', options: { responseCode: 404 } } } });
const deny = node({ type: 'n8n-nodes-base.respondToWebhook', version: 1.5, config: { name: 'رفض: مفتاح خاطئ', parameters: { respondWith: 'json', responseBody: '{"error": "unauthorized"}', options: { responseCode: 401 } } } });

// ------------- استلام الملفات والنشر على إنستغرام -------------
const pubHook = trigger({ type: 'n8n-nodes-base.webhook', version: 2.2, config: { name: 'استلام الملفات الجاهزة', parameters: { httpMethod: 'POST', path: 'fariz-publish', responseMode: 'onReceived' } } });
const prep = node({ type: 'n8n-nodes-base.code', version: 2, config: { name: 'تجهيز النشر', parameters: { mode: 'runOnceForAllItems', language: 'javaScript', jsCode: `const b = $input.first().json.body || {};
if (b.token !== '${TOKEN}') return [];
const images = Array.isArray(b.images) ? b.images : [];
let mode = 'review';
if (b.render_error) mode = 'error';
else if (b.publish === true || b.publish === 'true' || b.publish === 1) mode = 'publish';
return [{ json: { mode, row_id: Number(b.row_id), post_number: Number(b.post_number), type: b.type, images, video_url: b.video_url || '', cover_url: b.cover_url || '', caption: String(b.caption || '').slice(0, 2150), media_urls: JSON.stringify(b.video_url ? [b.video_url, b.cover_url] : images), error: String(b.render_error || '').slice(0, 900) } }];` } } });
const isPublish = ifElse({ version: 2.2, config: { name: 'نشر فعلي؟', parameters: { conditions: COND(expr('{{ $json.mode }}'), 'equals', 'publish') } } });
const saveReview = node({ type: 'n8n-nodes-base.dataTable', version: 1.1, config: { name: 'حفظ للمراجعة أو التصحيح', parameters: { resource: 'row', operation: 'update', dataTableId: TABLE, matchType: 'allConditions', filters: { conditions: [{ keyName: 'id', condition: 'eq', keyValue: expr('{{ $json.row_id }}') }] }, columns: { mappingMode: 'defineBelow', value: { status: expr('{{ $json.mode === "error" ? "NEEDS_CORRECTION" : "READY_FOR_REVIEW" }}'), media_urls: expr('{{ $json.media_urls }}'), error: expr('{{ $json.error }}') }, schema: [{ id: 'status', displayName: 'status', type: 'string', display: true }, { id: 'media_urls', displayName: 'media_urls', type: 'string', display: true }, { id: 'error', displayName: 'error', type: 'string', display: true }] } } } });

const me = node({ type: 'n8n-nodes-base.httpRequest', version: 4.2, config: { name: 'حساب إنستغرام', credentials: igCred, onError: 'continueErrorOutput', parameters: { method: 'GET', url: IG + 'me?fields=user_id,username', authentication: 'genericCredentialType', genericAuthType: 'httpQueryAuth', options: {} } } });
const containers = node({ type: 'n8n-nodes-base.code', version: 2, config: { name: 'تجهيز الحاويات', parameters: { mode: 'runOnceForAllItems', language: 'javaScript', jsCode: `const p = $('تجهيز النشر').first().json;
const ig = String($input.first().json.user_id || $input.first().json.id);
if (p.type === 'reel') return [{ json: { ig, kind: 'single', params: { media_type: 'REELS', video_url: p.video_url, cover_url: p.cover_url, caption: p.caption, share_to_feed: true } } }];
if (p.images.length > 1) return p.images.slice(0, 10).map(u => ({ json: { ig, kind: 'child', params: { image_url: u, is_carousel_item: true } } }));
return [{ json: { ig, kind: 'single', params: { image_url: p.images[0], caption: p.caption } } }];` } } });
const createMedia = node({ type: 'n8n-nodes-base.httpRequest', version: 4.2, config: { name: 'إنشاء حاوية الوسائط', credentials: igCred, onError: 'continueErrorOutput', retryOnFail: true, maxTries: 3, waitBetweenTries: 5000, parameters: { method: 'POST', url: expr(IG + '{{ $json.ig }}/media'), authentication: 'genericCredentialType', genericAuthType: 'httpQueryAuth', sendBody: true, specifyBody: 'json', jsonBody: expr('{{ JSON.stringify($json.params) }}'), options: {} } } });
const gather = node({ type: 'n8n-nodes-base.code', version: 2, config: { name: 'جمع الحاويات', parameters: { mode: 'runOnceForAllItems', language: 'javaScript', jsCode: `const p = $('تجهيز النشر').first().json;
const ids = $input.all().map(i => i.json.id).filter(Boolean);
const ig = $('تجهيز الحاويات').first().json.ig;
const carousel = p.type !== 'reel' && p.images.length > 1;
return [{ json: { ig, carousel: carousel ? 'yes' : 'no', creation_id: carousel ? '' : ids[0], params: { media_type: 'CAROUSEL', children: ids.join(','), caption: p.caption } } }];` } } });
const isCarousel = ifElse({ version: 2.2, config: { name: 'كاروسيل؟', parameters: { conditions: COND(expr('{{ $json.carousel }}'), 'equals', 'yes') } } });
const createCarousel = node({ type: 'n8n-nodes-base.httpRequest', version: 4.2, config: { name: 'إنشاء حاوية الكاروسيل', credentials: igCred, onError: 'continueErrorOutput', parameters: { method: 'POST', url: expr(IG + '{{ $json.ig }}/media'), authentication: 'genericCredentialType', genericAuthType: 'httpQueryAuth', sendBody: true, specifyBody: 'json', jsonBody: expr('{{ JSON.stringify($json.params) }}'), options: {} } } });
const wait = node({ type: 'n8n-nodes-base.wait', version: 1.1, config: { name: 'انتظار المعالجة', parameters: { resume: 'timeInterval', amount: 20, unit: 'seconds' } } });
const status = node({ type: 'n8n-nodes-base.httpRequest', version: 4.2, config: { name: 'حالة الحاوية', credentials: igCred, onError: 'continueErrorOutput', parameters: { method: 'GET', url: expr(IG + '{{ $json.creation_id || $json.id }}?fields=status_code,id'), authentication: 'genericCredentialType', genericAuthType: 'httpQueryAuth', options: {} } } });
const finished = ifElse({ version: 2.2, config: { name: 'جاهزة للنشر؟', parameters: { conditions: COND(expr('{{ $json.status_code }}'), 'equals', 'FINISHED') } } });
const stillOk = ifElse({ version: 2.2, config: { name: 'ما زالت تُعالج؟', parameters: { conditions: COND(expr('{{ ($json.status_code === "IN_PROGRESS" && $runIndex < 40) ? "wait" : "stop" }}'), 'equals', 'wait') } } });
const doPublish = node({ type: 'n8n-nodes-base.httpRequest', version: 4.2, config: { name: 'نشر المنشور', credentials: igCred, onError: 'continueErrorOutput', retryOnFail: true, maxTries: 3, waitBetweenTries: 5000, parameters: { method: 'POST', url: expr(IG + '{{ $("جمع الحاويات").first().json.ig }}/media_publish'), authentication: 'genericCredentialType', genericAuthType: 'httpQueryAuth', sendBody: true, specifyBody: 'json', jsonBody: expr('{{ JSON.stringify({ creation_id: $json.id }) }}'), options: {} } } });
const permalink = node({ type: 'n8n-nodes-base.httpRequest', version: 4.2, config: { name: 'رابط المنشور', credentials: igCred, onError: 'continueRegularOutput', parameters: { method: 'GET', url: expr(IG + '{{ $json.id }}?fields=id,permalink,timestamp'), authentication: 'genericCredentialType', genericAuthType: 'httpQueryAuth', options: {} } } });
const savePublished = node({ type: 'n8n-nodes-base.dataTable', version: 1.1, config: { name: 'تسجيل النشر', parameters: { resource: 'row', operation: 'update', dataTableId: TABLE, matchType: 'allConditions', filters: { conditions: [{ keyName: 'id', condition: 'eq', keyValue: expr('{{ $("تجهيز النشر").first().json.row_id }}') }] }, columns: { mappingMode: 'defineBelow', value: { status: 'PUBLISHED', ig_media_id: expr('{{ $("نشر المنشور").first().json.id }}'), permalink: expr('{{ $json.permalink || "" }}'), published_at: expr('{{ $now.toISO() }}'), media_urls: expr('{{ $("تجهيز النشر").first().json.media_urls }}'), error: '' }, schema: [{ id: 'status', displayName: 'status', type: 'string', display: true }, { id: 'ig_media_id', displayName: 'ig_media_id', type: 'string', display: true }, { id: 'permalink', displayName: 'permalink', type: 'string', display: true }, { id: 'published_at', displayName: 'published_at', type: 'date', display: true }, { id: 'media_urls', displayName: 'media_urls', type: 'string', display: true }, { id: 'error', displayName: 'error', type: 'string', display: true }] } } } });
const failMsg = node({ type: 'n8n-nodes-base.code', version: 2, config: { name: 'سبب الفشل', parameters: { mode: 'runOnceForAllItems', language: 'javaScript', jsCode: `const j = $input.first().json || {};
const msg = j.error ? (typeof j.error === 'string' ? j.error : JSON.stringify(j.error)) : (j.status_code ? 'حالة الحاوية: ' + j.status_code : JSON.stringify(j));
return [{ json: { row_id: $('تجهيز النشر').first().json.row_id, error: String(msg).slice(0, 900) } }];` } } });
const saveFailed = node({ type: 'n8n-nodes-base.dataTable', version: 1.1, config: { name: 'تسجيل الفشل', parameters: { resource: 'row', operation: 'update', dataTableId: TABLE, matchType: 'allConditions', filters: { conditions: [{ keyName: 'id', condition: 'eq', keyValue: expr('{{ $json.row_id }}') }] }, columns: { mappingMode: 'defineBelow', value: { status: 'FAILED', error: expr('{{ $json.error }}'), media_urls: expr('{{ $("تجهيز النشر").first().json.media_urls }}') }, schema: [{ id: 'status', displayName: 'status', type: 'string', display: true }, { id: 'error', displayName: 'error', type: 'string', display: true }, { id: 'media_urls', displayName: 'media_urls', type: 'string', display: true }] } } } });

const note1 = sticky('## تسليم المنشور التالي\nمحرك التصميم في GitHub يطلب هذا الرابط بالمفتاح السري، فيأخذ أقدم منشور APPROVED (أو منشورًا عالقًا أكثر من 3 ساعات) ويعلّمه DESIGNING.', [], { color: 4, width: 520, height: 160 });
const note2 = sticky('## النشر على إنستغرام (API الرسمي)\nيستلم روابط الصور/الفيديو بعد التصميم. إذا كان النشر مفعّلًا: ينشئ الحاوية (صورة/كاروسيل/Reel)، ينتظر المعالجة، ينشر، ويسجّل الرابط. أي فشل يُسجَّل FAILED مع السبب ولا يُكرَّر النشر.\nيحتاج اعتماد «Instagram FARIZ KANAAN (access_token)».', [], { color: 5, width: 620, height: 200 });

export default workflow('fariz-publish', 'FARIZ KANAAN - التسليم والنشر على إنستغرام')
  .add(note1)
  .add(nextHook)
  .to(tokenOk.onTrue(getReady.to(pickNext.to(found.onTrue(markDesigning.to(sendPost)).onFalse(none)))).onFalse(deny))
  .add(note2)
  .add(pubHook)
  .to(prep)
  .to(isPublish.onTrue(me).onFalse(saveReview))
  .add(me.onError(failMsg))
  .add(createMedia.onError(failMsg))
  .add(createCarousel.onError(failMsg))
  .add(status.onError(failMsg))
  .add(doPublish.onError(failMsg))
  .add(me)
  .to(containers)
  .to(createMedia)
  .to(gather)
  .to(isCarousel.onTrue(createCarousel.to(wait)).onFalse(wait))
  .add(wait)
  .to(status)
  .to(finished.onTrue(doPublish.to(permalink.to(savePublished))).onFalse(stillOk.onTrue(wait).onFalse(failMsg.to(saveFailed))));
