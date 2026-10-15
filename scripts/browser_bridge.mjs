import {pathToFileURL} from 'node:url';

export function endpointOrigin(value) {
  const parsed = new URL(value);
  if (parsed.protocol !== 'http:' || !['127.0.0.1', '[::1]'].includes(parsed.hostname) || !parsed.port || parsed.username || parsed.password || parsed.search || parsed.hash || parsed.pathname !== '/') throw new Error('Explicit loopback HTTP origin required');
  return parsed.origin;
}

export function redact(value) {
  return String(value).replace(/https?:\/\/\S+/gi, '[URL]').replace(/\S*(?:X-Amz-|Security-Token|Signature=|token=)\S*/gi, '[secret URL redacted]').replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, '[email]').replace(/\b(?:\d{1,3}\.){3}\d{1,3}\b/g, '[IP]');
}

export function blocked(state) {
  return [401, 403, 418, 429].includes(state.status) || /security verification|verify you are human|captcha|access denied|request verification|just a moment|正在进行安全验证|请稍候/i.test((state.title || '') + ' ' + (state.text || ''));
}

export class Channel {
  constructor(address, origin, timeout = 10000) {
    const parsed = new URL(address);
    if (parsed.protocol !== 'ws:' || parsed.host !== new URL(origin).host || parsed.username || parsed.password || parsed.search || parsed.hash) throw new Error('Unexpected CDP endpoint');
    this.socket = new WebSocket(address);
    this.sequence = 0;
    this.pending = new Map();
    this.closed = false;
    this.timeout = timeout;
    this.ready = new Promise((resolve, reject) => {
      const timer = setTimeout(() => { reject(new Error('Browser connection timed out')); this.close(); }, timeout);
      this.socket.addEventListener('open', () => {clearTimeout(timer); resolve();}, {once:true});
      this.socket.addEventListener('error', () => {clearTimeout(timer); reject(new Error('Browser connection failed')); this.close();}, {once:true});
      this.socket.addEventListener('close', () => {clearTimeout(timer); reject(new Error('Browser connection closed'));}, {once:true});
    });
    this.ready.catch(() => {});
    this.socket.addEventListener('close', () => this.close());
    this.socket.addEventListener('message', event => {
      const message = JSON.parse(event.data);
      const pending = this.pending.get(message.id);
      if (!pending) return;
      clearTimeout(pending.timer);
      this.pending.delete(message.id);
      message.error ? pending.reject(new Error('Browser command rejected')) : pending.resolve(message.result);
    });
  }
  async send(method, params = {}) {
    await this.ready;
    if (this.closed) throw new Error('Browser connection closed');
    const identifier = ++this.sequence;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {this.pending.delete(identifier); reject(new Error('Browser command timed out'));}, this.timeout);
      this.pending.set(identifier, {resolve, reject, timer});
      try { this.socket.send(JSON.stringify({id:identifier, method, params})); }
      catch {clearTimeout(timer); this.pending.delete(identifier); reject(new Error('Browser send failed'));}
    });
  }
  close() {
    if (this.closed) return;
    this.closed = true;
    for (const pending of this.pending.values()) {clearTimeout(pending.timer); pending.reject(new Error('Browser connection closed'));}
    this.pending.clear();
    try {this.socket.close();} catch {}
  }
}

async function targetsAt(origin) {
  const response = await fetch(origin + '/json/list', {redirect:'error', signal:AbortSignal.timeout(5000)});
  if (!response.ok) throw new Error('Browser endpoint unavailable');
  const body = await response.text();
  if (body.length > 2000000) throw new Error('Browser inventory too large');
  const targets = JSON.parse(body);
  if (!Array.isArray(targets)) throw new Error('Invalid browser inventory');
  return targets;
}

function hostAllowed(target, hosts) {
  try {
    const parsed = new URL(target.url);
    return parsed.protocol === 'https:' && hosts.some(host => parsed.hostname === host || parsed.hostname.endsWith('.' + host));
  } catch {return false;}
}

function safeTarget(target) {
  const parsed = new URL(target.url);
  return {id:target.id, type:target.type, host:parsed.hostname, title:redact(target.title), path:parsed.pathname.includes('http') ? '[embedded document]' : redact(parsed.pathname)};
}

async function inspect(channel) {
  const result = await channel.send('Runtime.evaluate', {returnByValue:true, expression:`(() => ({title:document.title, text:(document.body?.innerText || '').slice(0,2200), status:performance.getEntriesByType('navigation')[0]?.responseStatus || null, controls:[...document.querySelectorAll('a,button')].filter(element=>element.getClientRects().length).map(element=>({label:(element.getAttribute('aria-label') || element.getAttribute('title') || element.innerText || '').slice(0,160),tag:element.tagName})).filter(element=>/pdf|download|下载|全文/i.test(element.label)).slice(0,30)}))()`});
  if (result.exceptionDetails || !result.result?.value) throw new Error('Cannot inspect visible page');
  const value = result.result.value;
  return {...value, title:redact(value.title), text:redact(value.text), controls:value.controls.map(control=>({...control,label:redact(control.label)}))};
}

export async function run(options) {
  const origin = endpointOrigin(options.endpoint);
  if (!['probe','inspect','click'].includes(options.action) || !options.hosts?.length || options.hosts.some(host=>!/^([a-z0-9-]+\.)*[a-z0-9-]+$/.test(host))) throw new Error('Action and explicit allowed hosts required');
  const targets = await targetsAt(origin);
  if (options.action === 'probe') return {status:'connected_not_authenticated', targets:targets.filter(target=>target.type==='page' && hostAllowed(target, options.hosts)).map(safeTarget), cookies_read:false};
  const target = targets.find(item=>item.id===options.target && item.type==='page' && hostAllowed(item, options.hosts));
  if (!target) throw new Error('Authorized visible target not found');
  const channel = new Channel(target.webSocketDebuggerUrl, origin);
  try {
    const before = await inspect(channel);
    if (blocked(before)) return {status:'challenge_or_block', target:safeTarget(target), before, clicked:false};
    if (options.action === 'inspect') return {status:'observed_not_downloaded', target:safeTarget(target), before};
    if (!options.label || !before.controls.some(control=>control.label===options.label) || !/pdf|download|下载|全文/i.test(options.label)) throw new Error('Exact observed PDF control required');
    const result = await channel.send('Runtime.evaluate', {returnByValue:true, userGesture:true, expression:`(() => { const label=${JSON.stringify(options.label)}; const matches=[...document.querySelectorAll('a,button')].filter(element=>element.getClientRects().length && (element.getAttribute('aria-label') || element.getAttribute('title') || element.innerText || '')===label); if(matches.length!==1) return {clicked:false,reason:'ambiguous_control'}; matches[0].click(); return {clicked:true}; })()`});
    await new Promise(resolve=>setTimeout(resolve, 1500));
    const afterTargets = await targetsAt(origin);
    const previousIds = new Set(targets.map(item=>item.id));
    const added = afterTargets.filter(item=>!previousIds.has(item.id));
    const challenge = added.some(item=>item.url?.startsWith('https://challenges.cloudflare.com/') || blocked({title:item.title}));
    const after = afterTargets.some(item=>item.id===target.id) ? await inspect(channel) : null;
    return {status:challenge || after && blocked(after) ? 'challenge_or_block' : 'clicked_not_downloaded', target:safeTarget(target), before, after, click:result.result?.value, new_targets:added.filter(item=>hostAllowed(item, options.hosts)).map(safeTarget)};
  } finally {channel.close();}
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const watchdog = setTimeout(()=>{console.log(JSON.stringify({status:'browser_timeout'})); process.exit(2);}, 45000);
  try {
    const options = JSON.parse(process.argv[2]);
    const result = await run(options);
    console.log(JSON.stringify(result));
    if (result.status === 'challenge_or_block') process.exitCode = 3;
  } catch (error) {console.log(JSON.stringify({status:'browser_error', error:redact(error.message)})); process.exitCode = 2;}
  finally {clearTimeout(watchdog);}
}
