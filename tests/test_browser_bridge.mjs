import test from 'node:test';
import assert from 'node:assert/strict';
import {endpointOrigin, blocked, redact, Channel, run} from '../scripts/browser_bridge.mjs';

test('only explicit loopback endpoints are accepted', () => {
  assert.equal(endpointOrigin('http://127.0.0.1:9333'), 'http://127.0.0.1:9333');
  for (const value of ['http://localhost:9222','http://192.168.1.1:9222','http://127.0.0.1:9222/path','http://127.0.0.1:9222/'+'?'+'key=value','http://user@127.0.0.1:9222']) assert.throws(()=>endpointOrigin(value));
});

test('English Chinese and HTTP challenges stop', () => {
  for (const status of [401,403,418,429]) assert.equal(blocked({status}),true);
  for (const title of ['Security verification','请稍候','正在进行安全验证']) assert.equal(blocked({status:200,title}),true);
  assert.equal(blocked({status:200,title:'Article',text:'Full Access'}),false);
});

test('signed URLs and email values are removed', () => {
  const secret='private'+'-secret';
  const address='https://publisher.example/file.pdf?token'+'='+secret;
  assert.equal(redact(address),'[URL]');
  assert.equal(redact('reader'+'@'+'example.edu'),'[email]');
  assert.ok(!redact(address).includes(secret));
});

test('untrusted websocket locations are rejected before connection', () => {
  assert.throws(()=>new Channel('ws://192.168.1.1:9222/devtools/page/1','http://127.0.0.1:9222'));
  assert.throws(()=>new Channel('ws://127.0.0.1:9333/devtools/page/1','http://127.0.0.1:9222'));
});

test('probe hides unrelated tabs and signed query strings', async context => {
  const url = 'https://publisher.example/paper.pdf' + '?' + 'token=synthetic';
  context.mock.method(globalThis, 'fetch', async () => ({ok:true, text:async()=>JSON.stringify([{id:'visible',type:'page',url,title:'Article'},{id:'private-tab',type:'page',url:'https://unrelated.example/account',title:'Private'}])}));
  const result = await run({endpoint:'http://127.0.0.1:9333',action:'probe',hosts:['publisher.example']});
  assert.equal(result.targets.length,1);
  assert.equal(result.targets[0].path,'/paper.pdf');
  assert.ok(!JSON.stringify(result).includes('token='));
  assert.ok(!JSON.stringify(result).includes('Private'));
});

test('command timeout is bounded and pending calls are cleaned', async context => {
  class SilentSocket extends EventTarget {
    constructor() {super(); queueMicrotask(()=>this.dispatchEvent(new Event('open')));}
    send() {}
    close() {this.dispatchEvent(new Event('close'));}
  }
  context.mock.property(globalThis, 'WebSocket', SilentSocket);
  const channel = new Channel('ws://127.0.0.1:9333/devtools/page/demo','http://127.0.0.1:9333',20);
  await assert.rejects(channel.send('Runtime.evaluate'), /timed out/);
  channel.close();
  assert.equal(channel.pending.size,0);
  assert.equal(channel.closed,true);
});

test('a challenge is observed without clicking or reading cookies', async context => {
  const methods = [];
  class ChallengeSocket extends EventTarget {
    constructor() {super(); queueMicrotask(()=>this.dispatchEvent(new Event('open')));}
    send(payload) {
      const request=JSON.parse(payload);
      methods.push(request.method);
      assert.ok(!request.params.expression.includes('matches[0].click'));
      queueMicrotask(()=>this.dispatchEvent(new MessageEvent('message',{data:JSON.stringify({id:request.id,result:{result:{value:{title:'Security verification',text:'',status:200,controls:[]}}}})})));
    }
    close() {this.dispatchEvent(new Event('close'));}
  }
  context.mock.property(globalThis, 'WebSocket', ChallengeSocket);
  context.mock.method(globalThis,'fetch',async()=>({ok:true,text:async()=>JSON.stringify([{id:'demo',type:'page',url:'https://publisher.example/article',title:'Article',webSocketDebuggerUrl:'ws://127.0.0.1:9333/devtools/page/demo'}])}));
  const result=await run({endpoint:'http://127.0.0.1:9333',action:'click',target:'demo',label:'Download PDF',hosts:['publisher.example']});
  assert.equal(result.status,'challenge_or_block');
  assert.equal(result.clicked,false);
  assert.deepEqual(methods,['Runtime.evaluate']);
});
