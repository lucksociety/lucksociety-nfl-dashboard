"""Symmetric, market-free estimators with chronological model selection."""
import json, math, hashlib, os
os.environ.setdefault('OMP_NUM_THREADS','2')
import numpy as np
from scipy.special import expit,logit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import log_loss,roc_auc_score
from .features import NAMES
METHODS=['KO','SUB','DEC']

def estimator(kind):
    if kind=='logistic':return make_pipeline(StandardScaler(),LogisticRegression(C=.1,fit_intercept=False,max_iter=1000))
    return HistGradientBoostingClassifier(max_iter=100,max_leaf_nodes=7,min_samples_leaf=60,l2_regularization=10,learning_rate=.05,random_state=731,early_stopping=False)

def strength_inputs(X):
    # Missing profile fields reflect source coverage, not fighting ability.
    # Preserve indicators in feature archives/quality gates but forbid them as outcome shortcuts.
    X=np.atleast_2d(X).copy();X[:,21:24]=0;return X

def fit(kind,X,y):
    X=strength_inputs(X)
    if kind=='elo':return None
    m=estimator(kind);m.fit(np.vstack([X,-X]),np.r_[y,1-y]);return m

def probability(model,X,kind,temperature=1):
    X=strength_inputs(X)
    if kind=='elo':p=expit(X[:,0]*math.log(10))
    else:p=(model.predict_proba(X)[:,1]+1-model.predict_proba(-X)[:,1])/2
    return expit(logit(np.clip(p,1e-6,1-1e-6))/temperature)

def metrics(y,p):
    if not len(y):return dict(n=0)
    p=np.asarray(p);y=np.asarray(y);bins=[]
    for lo in np.arange(0,1,.1):
        mask=(p>=lo)&(p<lo+.1 if lo<.9 else p<=1)
        if mask.any():bins.append(dict(n=int(mask.sum()),probability=float(p[mask].mean()),frequency=float(y[mask].mean())))
    return dict(n=len(y),log_loss=float(log_loss(y,p,labels=[0,1])),brier=float(np.mean((p-y)**2)),accuracy=float(np.mean((p>.5)==y)),auc=float(roc_auc_score(y,p))if len(set(y))>1 else None,ece=sum(b['n']*abs(b['probability']-b['frequency'])for b in bins)/len(y),reliability=bins)

def temperature(y,p):
    grid=[.8,1.,1.15,1.3,1.5,1.8,2.2]
    return min(grid,key=lambda t:log_loss(y,expit(logit(np.clip(p,1e-6,1-1e-6))/t),labels=[0,1]))

class Model:
    def __init__(self,kind,base,temp,method_model,method_prior):self.kind=kind;self.base=base;self.temperature=temp;self.method_model=method_model;self.method_prior=method_prior
    def predict(self,x,rounds):
        p=float(probability(self.base,x,self.kind,self.temperature)[0]);conds=[]
        for sign in [1,-1]:
            if self.method_model is None:q=self.method_prior
            else:
                raw=self.method_model.predict_proba(np.r_[sign*strength_inputs(x)[0],rounds==5].reshape(1,-1))[0];q=np.array([raw[list(self.method_model.classes_).index(k)]if k in self.method_model.classes_ else 0 for k in METHODS])
            conds.append(q)
        joint=np.r_[p*conds[0],(1-p)*conds[1]]
        return dict(win=[p,1-p],methods=dict(zip(['A_'+k for k in METHODS]+['B_'+k for k in METHODS],map(float,joint))),distance=float(joint[2]+joint[5]))

def fit_method(X,bouts):
    # Method conditional on the winner; no red/blue shortcut and no post-fight features.
    y=np.array([b['method']for b in bouts]);z=np.array([np.r_[x if b['y']else-x,b['rounds']==5]for x,b in zip(strength_inputs(X),bouts)])
    prior=np.array([(sum(y==k)+2)/(len(y)+6)for k in METHODS])
    if len(set(y))<3:return None,prior
    m=make_pipeline(StandardScaler(),LogisticRegression(C=.05,max_iter=1000));m.fit(z,y);return m,prior

def train(X,bouts,output,now_day):
    output.mkdir(parents=True,exist_ok=True);days=np.array([b['date']for b in bouts]);y=np.array([b['y']for b in bouts])
    # Fixed temporal boundaries are committed before viewing final-test results.
    train=days<'2023-01-01';cal=(days>='2023-01-01')&(days<'2024-01-01');valid=(days>='2024-01-01')&(days<'2024-11-01');test=(days>='2024-11-01')&(days<now_day)
    if min(train.sum(),cal.sum(),valid.sum(),test.sum())<100:raise ValueError('Insufficient chronological validation coverage')
    results={};fitted={}
    for kind in ['elo','logistic','boosting']:
        base=fit(kind,X[train],y[train]);t=temperature(y[cal],probability(base,X[cal],kind));p=probability(base,X[valid],kind,t)
        losses=-(y[valid]*np.log(np.clip(p,1e-9,1))+(1-y[valid])*np.log(np.clip(1-p,1e-9,1)))
        event_losses={}
        for day,loss in zip(days[valid],losses):event_losses.setdefault(day,[]).append(float(loss))
        se=float(np.std([np.mean(v)for v in event_losses.values()],ddof=1)/np.sqrt(len(event_losses)))
        results[kind]=dict(temperature=t,validation=metrics(y[valid],p),event_logloss_se=se);fitted[kind]=(base,t)
    best=min(results,key=lambda k:results[k]['validation']['log_loss'])
    threshold=results[best]['validation']['log_loss']+results[best]['event_logloss_se']
    chosen=next(k for k in ['elo','logistic','boosting']if results[k]['validation']['log_loss']<=threshold)
    # The final test is evaluated only AFTER architecture/temperature selection is complete.
    all_development=days<'2024-11-01';base=fit(chosen,X[all_development],y[all_development]);t=results[chosen]['temperature'];p=probability(base,X[test],chosen,t)
    elo_p=probability(None,X[test],'elo',results['elo']['temperature'])
    method_model,prior=fit_method(X[all_development],[b for b,m in zip(bouts,all_development)if m]);test_model=Model(chosen,base,t,method_model,prior)
    method_losses=[]
    for x,b in zip(X[test],[b for b,m in zip(bouts,test)if m]):
        pred=test_model.predict(x,b['rounds']);key=('A_'if b['y']else'B_')+b['method'];method_losses.append(-math.log(max(1e-9,pred['methods'][key])))
    segments={}
    selected=[b for b,m in zip(bouts,test)if m]
    for weight in sorted({b['weight']for b in selected}):
        mask=np.array([b['weight']==weight for b in selected]);segments[weight]=metrics(y[test][mask],p[mask])
    # Entry count is carried separately; rounded prior/experience differences cannot identify both debutants.
    for label,mask in [('five_round',np.array([b['rounds']==5 for b in selected])),('debutant',np.array([min(b['experience'])==0 for b in selected])),('heavy_favorite',np.maximum(p,1-p)>=.75)]:segments[label]=metrics(y[test][mask],p[mask])
    report=dict(selection_rule='Simplest candidate within one event-level standard error of best validation log loss; no test-based selection',
                holdout_status='Historical diagnostic: initial development test was inspected during construction; future published forecasts are the untouched prospective test.',
                protocol='Architecture/temperature chosen on 2023 calibration + Jan–Oct 2024 validation; final frozen-model test Nov 2024 onward, then refit for live use',boundaries={'training_before':'2023-01-01','calibration_before':'2024-01-01','validation_before':'2024-11-01','test_before':now_day},candidates=results,selected=chosen,test=metrics(y[test],p),elo_test=metrics(y[test],elo_p),joint_method_log_loss=float(np.mean(method_losses)),segments=segments,market_benchmark={'available':False,'reason':'No independently verified timestamped closing-odds series was found; no market-superiority or historical betting ROI claim.'},limitations=['Men only; standard modern 3/5-round UFC bouts; draws/NC/DQ excluded','Dated pre-UFC evidence is collected separately; it is not yet a validated scoring feature. No injury/weight-cut clearance or short-notice timestamps','Debutants use explicit shrunk priors; no bets with fewer than two UFC bouts each','Method model is conditional multinomial regression; finish-round and totals models are not supplied','Historical physical metadata comes from current source snapshots; career aggregate stats are never used','Direct UFCStats challenge is not bypassed; source is a third-party snapshot with content hashes'])
    # Final test report is a versioned artifact, never a signal for automatic model selection.
    (output/'evaluation.json').write_text(json.dumps(report,indent=2)+'\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(5,5));bins=report['test']['reliability'];ax.plot([0,1],[0,1],'--',color='gray');ax.plot([b['probability']for b in bins],[b['frequency']for b in bins],'o-');ax.set(xlabel='Predicted P(A wins)',ylabel='Observed A win rate',title='UFC held-out calibration');fig.tight_layout();fig.savefig(output/'calibration.png');plt.close(fig)
    live=fit(chosen,X,y);method_model,prior=fit_method(X,bouts);model=Model(chosen,live,t,method_model,prior)
    import joblib
    joblib.dump(model,output/'model.joblib')
    (output/'model.json').write_text(json.dumps(dict(version='ufc-1.1.0',selected=chosen,temperature=t,features=NAMES,train_bouts=len(bouts),data_through=max(days),methods=METHODS),indent=2))
    return model,report
