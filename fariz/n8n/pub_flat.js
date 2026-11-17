import { workflow, node, trigger, sticky, ifElse, switchCase, expr, newCredential } from '@n8n/workflow-sdk';

const n29 = sticky("## تسليم المنشور التالي\nمحرك التصميم في GitHub يطلب هذا الرابط بالمفتاح السري، فيأخذ أقدم منشور APPROVED (أو منشورًا عالقًا أكثر من 3 ساعات) ويعلّمه DESIGNING.", [], { "color": 4, "width": 520, "height": 160 });

const n1 = trigger({ "type": "n8n-nodes-base.webhook", "version": 2.2, "config": { "name": "طلب المنشور التالي", "parameters": { "httpMethod": "GET", "path": "fariz-next", "responseMode": "responseNode" } } });

const n2 = ifElse({ "version": 2.2, "config": { "name": "المفتاح صحيح؟", "parameters": { "conditions": { "options": { "caseSensitive": true, "leftValue": "", "typeValidation": "loose" }, "conditions": [{ "leftValue": expr("{{ $json.query?.token ?? \"\" }}"), "operator": { "type": "string", "operation": "equals" }, "rightValue": "1891f7bfe9498d518871e914ba10d0cb440938dc" }], "combinator": "and" } } } });

const n3 = node({ "type": "n8n-nodes-base.dataTable", "version": 1.1, "config": { "name": "جلب الجاهز للتصميم", "alwaysOutputData": true, "parameters": { "resource": "row", "operation": "get", "dataTableId": { "__rl": true, "mode": "id", "value": "xxdPIIe3xCVSZR44", "cachedResultName": "fariz_queue" }, "matchType": "anyCondition", "filters": { "conditions": [{ "keyName": "status", "condition": "eq", "keyValue": "APPROVED" }, { "keyName": "status", "condition": "eq", "keyValue": "DESIGNING" }] }, "returnAll": false, "limit": 100, "orderBy": true, "orderByColumn": "post_number", "orderByDirection": "ASC" } } });

const n4 = node({ "type": "n8n-nodes-base.code", "version": 2, "config": { "name": "اختيار المنشور", "parameters": { "mode": "runOnceForAllItems", "language": "javaScript", "jsCode": "const rows = $input.all().map(i => i.json).filter(r => r.id);\nconst want = Number($('طلب المنشور التالي').first().json.query?.post || 0);\nconst old = Date.now() - 3 * 3600 * 1000;\nlet hit = want ? rows.find(r => r.post_number === want) : null;\nhit = hit || rows.find(r => r.status === 'DESIGNING' && new Date(r.updatedAt).getTime() < old) || rows.find(r => r.status === 'APPROVED');\nreturn [{ json: hit ? { found: 'yes', row_id: hit.id, post_number: hit.post_number, content: hit.content } : { found: 'no' } }];" } } });

const n5 = ifElse({ "version": 2.2, "config": { "name": "يوجد منشور؟", "parameters": { "conditions": { "options": { "caseSensitive": true, "leftValue": "", "typeValidation": "loose" }, "conditions": [{ "leftValue": expr("{{ $json.found }}"), "operator": { "type": "string", "operation": "equals" }, "rightValue": "yes" }], "combinator": "and" } } } });

const n6 = node({ "type": "n8n-nodes-base.dataTable", "version": 1.1, "config": { "name": "تعليمه قيد التصميم", "parameters": { "resource": "row", "operation": "update", "dataTableId": { "__rl": true, "mode": "id", "value": "xxdPIIe3xCVSZR44", "cachedResultName": "fariz_queue" }, "matchType": "allConditions", "filters": { "conditions": [{ "keyName": "id", "condition": "eq", "keyValue": expr("{{ $json.row_id }}") }] }, "columns": { "mappingMode": "defineBelow", "value": { "status": "DESIGNING" }, "schema": [{ "id": "status", "displayName": "status", "type": "string", "display": true }] } } } });

const n7 = node({ "type": "n8n-nodes-base.respondToWebhook", "version": 1.5, "config": { "name": "إرسال المنشور", "parameters": { "respondWith": "json", "responseBody": expr("{{ JSON.stringify($(\"اختيار المنشور\").first().json) }}") } } });

const n8 = node({ "type": "n8n-nodes-base.respondToWebhook", "version": 1.5, "config": { "name": "لا يوجد منشور جاهز", "parameters": { "respondWith": "json", "responseBody": "{\"empty\": true}", "options": { "responseCode": 404 } } } });

const n9 = node({ "type": "n8n-nodes-base.respondToWebhook", "version": 1.5, "config": { "name": "رفض: مفتاح خاطئ", "parameters": { "respondWith": "json", "responseBody": "{\"error\": \"unauthorized\"}", "options": { "responseCode": 401 } } } });

const n30 = sticky("## النشر على إنستغرام (API الرسمي)\nيستلم روابط الصور/الفيديو بعد التصميم. إذا كان النشر مفعّلًا: ينشئ الحاوية (صورة/كاروسيل/Reel)، ينتظر المعالجة، ينشر، ويسجّل الرابط. أي فشل يُسجَّل FAILED مع السبب ولا يُكرَّر النشر.\nيحتاج اعتماد «Instagram FARIZ KANAAN (access_token)».", [], { "color": 5, "width": 620, "height": 200 });

const n10 = trigger({ "type": "n8n-nodes-base.webhook", "version": 2.2, "config": { "name": "استلام الملفات الجاهزة", "parameters": { "httpMethod": "POST", "path": "fariz-publish", "responseMode": "onReceived" } } });

const n11 = node({ "type": "n8n-nodes-base.code", "version": 2, "config": { "name": "تجهيز النشر", "parameters": { "mode": "runOnceForAllItems", "language": "javaScript", "jsCode": "const b = $input.first().json.body || {};\nif (b.token !== '1891f7bfe9498d518871e914ba10d0cb440938dc') return [];\nconst images = Array.isArray(b.images) ? b.images : [];\nlet mode = 'review';\nif (b.render_error) mode = 'error';\nelse if (b.publish === true || b.publish === 'true' || b.publish === 1) mode = 'publish';\nreturn [{ json: { mode, row_id: Number(b.row_id), post_number: Number(b.post_number), type: b.type, images, video_url: b.video_url || '', cover_url: b.cover_url || '', caption: String(b.caption || '').slice(0, 2150), media_urls: JSON.stringify(b.video_url ? [b.video_url, b.cover_url] : images), error: String(b.render_error || '').slice(0, 900) } }];" } } });

const n12 = ifElse({ "version": 2.2, "config": { "name": "نشر فعلي؟", "parameters": { "conditions": { "options": { "caseSensitive": true, "leftValue": "", "typeValidation": "loose" }, "conditions": [{ "leftValue": expr("{{ $json.mode }}"), "operator": { "type": "string", "operation": "equals" }, "rightValue": "publish" }], "combinator": "and" } } } });

const n14 = node({ "type": "n8n-nodes-base.httpRequest", "version": 4.2, "config": { "name": "حساب إنستغرام", "credentials": { "httpQueryAuth": newCredential("Instagram FARIZ KANAAN (access_token)") }, "onError": "continueErrorOutput", "parameters": { "method": "GET", "url": "https://graph.instagram.com/v23.0/me?fields=user_id,username", "authentication": "genericCredentialType", "genericAuthType": "httpQueryAuth", "options": {  } } } });

const n27 = node({ "type": "n8n-nodes-base.code", "version": 2, "config": { "name": "سبب الفشل", "parameters": { "mode": "runOnceForAllItems", "language": "javaScript", "jsCode": "const j = $input.first().json || {};\nconst msg = j.error ? (typeof j.error === 'string' ? j.error : JSON.stringify(j.error)) : (j.status_code ? 'حالة الحاوية: ' + j.status_code : JSON.stringify(j));\nreturn [{ json: { row_id: $('تجهيز النشر').first().json.row_id, error: String(msg).slice(0, 900) } }];" } } });

const n13 = node({ "type": "n8n-nodes-base.dataTable", "version": 1.1, "config": { "name": "حفظ للمراجعة أو التصحيح", "parameters": { "resource": "row", "operation": "update", "dataTableId": { "__rl": true, "mode": "id", "value": "xxdPIIe3xCVSZR44", "cachedResultName": "fariz_queue" }, "matchType": "allConditions", "filters": { "conditions": [{ "keyName": "id", "condition": "eq", "keyValue": expr("{{ $json.row_id }}") }] }, "columns": { "mappingMode": "defineBelow", "value": { "status": expr("{{ $json.mode === \"error\" ? \"NEEDS_CORRECTION\" : \"READY_FOR_REVIEW\" }}"), "media_urls": expr("{{ $json.media_urls }}"), "error": expr("{{ $json.error }}") }, "schema": [{ "id": "status", "displayName": "status", "type": "string", "display": true }, { "id": "media_urls", "displayName": "media_urls", "type": "string", "display": true }, { "id": "error", "displayName": "error", "type": "string", "display": true }] } } } });

const n16 = node({ "type": "n8n-nodes-base.httpRequest", "version": 4.2, "config": { "name": "إنشاء حاوية الوسائط", "credentials": { "httpQueryAuth": newCredential("Instagram FARIZ KANAAN (access_token)") }, "onError": "continueErrorOutput", "retryOnFail": true, "maxTries": 3, "waitBetweenTries": 5000, "parameters": { "method": "POST", "url": expr("https://graph.instagram.com/v23.0/{{ $json.ig }}/media"), "authentication": "genericCredentialType", "genericAuthType": "httpQueryAuth", "sendBody": true, "specifyBody": "json", "jsonBody": expr("{{ JSON.stringify($json.params) }}"), "options": {  } } } });

const n19 = node({ "type": "n8n-nodes-base.httpRequest", "version": 4.2, "config": { "name": "إنشاء حاوية الكاروسيل", "credentials": { "httpQueryAuth": newCredential("Instagram FARIZ KANAAN (access_token)") }, "onError": "continueErrorOutput", "parameters": { "method": "POST", "url": expr("https://graph.instagram.com/v23.0/{{ $json.ig }}/media"), "authentication": "genericCredentialType", "genericAuthType": "httpQueryAuth", "sendBody": true, "specifyBody": "json", "jsonBody": expr("{{ JSON.stringify($json.params) }}"), "options": {  } } } });

const n20 = node({ "type": "n8n-nodes-base.wait", "version": 1.1, "config": { "name": "انتظار المعالجة", "parameters": { "resume": "timeInterval", "amount": 20, "unit": "seconds" } } });

const n21 = node({ "type": "n8n-nodes-base.httpRequest", "version": 4.2, "config": { "name": "حالة الحاوية", "credentials": { "httpQueryAuth": newCredential("Instagram FARIZ KANAAN (access_token)") }, "onError": "continueErrorOutput", "parameters": { "method": "GET", "url": expr("https://graph.instagram.com/v23.0/{{ $json.creation_id || $json.id }}?fields=status_code,id"), "authentication": "genericCredentialType", "genericAuthType": "httpQueryAuth", "options": {  } } } });

const n24 = node({ "type": "n8n-nodes-base.httpRequest", "version": 4.2, "config": { "name": "نشر المنشور", "credentials": { "httpQueryAuth": newCredential("Instagram FARIZ KANAAN (access_token)") }, "onError": "continueErrorOutput", "retryOnFail": true, "maxTries": 3, "waitBetweenTries": 5000, "parameters": { "method": "POST", "url": expr("https://graph.instagram.com/v23.0/{{ $(\"جمع الحاويات\").first().json.ig }}/media_publish"), "authentication": "genericCredentialType", "genericAuthType": "httpQueryAuth", "sendBody": true, "specifyBody": "json", "jsonBody": expr("{{ JSON.stringify({ creation_id: $json.id }) }}"), "options": {  } } } });

const n25 = node({ "type": "n8n-nodes-base.httpRequest", "version": 4.2, "config": { "name": "رابط المنشور", "credentials": { "httpQueryAuth": newCredential("Instagram FARIZ KANAAN (access_token)") }, "onError": "continueRegularOutput", "parameters": { "method": "GET", "url": expr("https://graph.instagram.com/v23.0/{{ $json.id }}?fields=id,permalink,timestamp"), "authentication": "genericCredentialType", "genericAuthType": "httpQueryAuth", "options": {  } } } });

const n26 = node({ "type": "n8n-nodes-base.dataTable", "version": 1.1, "config": { "name": "تسجيل النشر", "parameters": { "resource": "row", "operation": "update", "dataTableId": { "__rl": true, "mode": "id", "value": "xxdPIIe3xCVSZR44", "cachedResultName": "fariz_queue" }, "matchType": "allConditions", "filters": { "conditions": [{ "keyName": "id", "condition": "eq", "keyValue": expr("{{ $(\"تجهيز النشر\").first().json.row_id }}") }] }, "columns": { "mappingMode": "defineBelow", "value": { "status": "PUBLISHED", "ig_media_id": expr("{{ $(\"نشر المنشور\").first().json.id }}"), "permalink": expr("{{ $json.permalink || \"\" }}"), "published_at": expr("{{ $now.toISO() }}"), "media_urls": expr("{{ $(\"تجهيز النشر\").first().json.media_urls }}"), "error": "" }, "schema": [{ "id": "status", "displayName": "status", "type": "string", "display": true }, { "id": "ig_media_id", "displayName": "ig_media_id", "type": "string", "display": true }, { "id": "permalink", "displayName": "permalink", "type": "string", "display": true }, { "id": "published_at", "displayName": "published_at", "type": "date", "display": true }, { "id": "media_urls", "displayName": "media_urls", "type": "string", "display": true }, { "id": "error", "displayName": "error", "type": "string", "display": true }] } } } });

const n15 = node({ "type": "n8n-nodes-base.code", "version": 2, "config": { "name": "تجهيز الحاويات", "parameters": { "mode": "runOnceForAllItems", "language": "javaScript", "jsCode": "const p = $('تجهيز النشر').first().json;\nconst ig = String($input.first().json.user_id || $input.first().json.id);\nif (p.type === 'reel') return [{ json: { ig, kind: 'single', params: { media_type: 'REELS', video_url: p.video_url, cover_url: p.cover_url, caption: p.caption, share_to_feed: true } } }];\nif (p.images.length > 1) return p.images.slice(0, 10).map(u => ({ json: { ig, kind: 'child', params: { image_url: u, is_carousel_item: true } } }));\nreturn [{ json: { ig, kind: 'single', params: { image_url: p.images[0], caption: p.caption } } }];" } } });

const n17 = node({ "type": "n8n-nodes-base.code", "version": 2, "config": { "name": "جمع الحاويات", "parameters": { "mode": "runOnceForAllItems", "language": "javaScript", "jsCode": "const p = $('تجهيز النشر').first().json;\nconst ids = $input.all().map(i => i.json.id).filter(Boolean);\nconst ig = $('تجهيز الحاويات').first().json.ig;\nconst carousel = p.type !== 'reel' && p.images.length > 1;\nreturn [{ json: { ig, carousel: carousel ? 'yes' : 'no', creation_id: carousel ? '' : ids[0], params: { media_type: 'CAROUSEL', children: ids.join(','), caption: p.caption } } }];" } } });

const n18 = ifElse({ "version": 2.2, "config": { "name": "كاروسيل؟", "parameters": { "conditions": { "options": { "caseSensitive": true, "leftValue": "", "typeValidation": "loose" }, "conditions": [{ "leftValue": expr("{{ $json.carousel }}"), "operator": { "type": "string", "operation": "equals" }, "rightValue": "yes" }], "combinator": "and" } } } });

const n22 = ifElse({ "version": 2.2, "config": { "name": "جاهزة للنشر؟", "parameters": { "conditions": { "options": { "caseSensitive": true, "leftValue": "", "typeValidation": "loose" }, "conditions": [{ "leftValue": expr("{{ $json.status_code }}"), "operator": { "type": "string", "operation": "equals" }, "rightValue": "FINISHED" }], "combinator": "and" } } } });

const n23 = ifElse({ "version": 2.2, "config": { "name": "ما زالت تُعالج؟", "parameters": { "conditions": { "options": { "caseSensitive": true, "leftValue": "", "typeValidation": "loose" }, "conditions": [{ "leftValue": expr("{{ ($json.status_code === \"IN_PROGRESS\" && $runIndex < 40) ? \"wait\" : \"stop\" }}"), "operator": { "type": "string", "operation": "equals" }, "rightValue": "wait" }], "combinator": "and" } } } });

const n28 = node({ "type": "n8n-nodes-base.dataTable", "version": 1.1, "config": { "name": "تسجيل الفشل", "parameters": { "resource": "row", "operation": "update", "dataTableId": { "__rl": true, "mode": "id", "value": "xxdPIIe3xCVSZR44", "cachedResultName": "fariz_queue" }, "matchType": "allConditions", "filters": { "conditions": [{ "keyName": "id", "condition": "eq", "keyValue": expr("{{ $json.row_id }}") }] }, "columns": { "mappingMode": "defineBelow", "value": { "status": "FAILED", "error": expr("{{ $json.error }}"), "media_urls": expr("{{ $(\"تجهيز النشر\").first().json.media_urls }}") }, "schema": [{ "id": "status", "displayName": "status", "type": "string", "display": true }, { "id": "error", "displayName": "error", "type": "string", "display": true }, { "id": "media_urls", "displayName": "media_urls", "type": "string", "display": true }] } } } });

export default workflow("fariz-publish", "FARIZ KANAAN - التسليم والنشر على إنستغرام")
  .add(n29)
  .add(n1)
  .to(n2.onTrue(n3.to(n4.to(n5.onTrue(n6.to(n7)).onFalse(n8)))).onFalse(n9))
  .add(n30)
  .add(n10)
  .to(n11)
  .to(n12.onTrue(n14.onError(n27)).onFalse(n13))
  .add(n14.onError(n27))
  .add(n16.onError(n27))
  .add(n19.onError(n27).to(n20))
  .add(n21.onError(n27))
  .add(n24.onError(n27).to(n25.to(n26)))
  .add(n14.onError(n27))
  .to(n15)
  .to(n16.onError(n27))
  .to(n17)
  .to(n18.onTrue(n19.onError(n27).to(n20)).onFalse(n20))
  .add(n20)
  .to(n21.onError(n27))
  .to(n22.onTrue(n24.onError(n27).to(n25.to(n26))).onFalse(n23.onTrue(n20).onFalse(n27.to(n28))));
