#INTRASUBJECT VARIABILITY FROM CONFIDENCE INTERVAL
#if subject number in sequences not known, assume balanced design to get conservative estimate
#for parallel design, set n<-n1+n2 (!)
###=====================================================
##### Read table with confidence intervals from studies (.csv format)
setwd(r"(C:\Users\i0172484\OneDrive - ZENTIVA\Documents\01 - Projects\Linaprazan Jun2026\PARs Amoxicillin\CVw_02_manual)")
tab <- read.csv('CVw_Screening.csv',
#file.choose(),
header=TRUE,
sep=",",
skip=0,
as.is=TRUE,
na.strings="NA",
)
head(tab)

alpha		<- .05		#alpha
### WORKING ONLY FOR ONE POWER SO FAR
### RESHAPE DATAFRAME TO ACCOMODATE COLUMS FOR DIFFERENT POWERS
targetpower	<- c(.8, .9)	#required power 
theta0		<-c(.95)	#expected ratio
method		<-"exact"	#"exact" or "central" (Hauschke et al., 1992) or "non-central" approximation

res		<- matrix(ncol=length(targetpower), nrow=nrow(tab))
res     <- as.data.frame(res)

nmv		<- c()
for (tp in targetpower) {
nm <- paste("N-Pwr", tp *100 , "%", sep = "")
nmv <- append(nmv, nm)
}
colnames(res) <- nmv
print(res)


# res <- c()
CVcol <- c()
library(PowerTOST)
r = 1
for (r in 1:nrow(tab)) {
n		<- tab[r, c("Ntotal")]			#number of subjects
point 	<- tab[r, c("Point")]	#point estimate (if not given, type "NA")
lower 	<- tab[r, c("lower")] 	#lower limit of 100*(1-2*alpha)% confidence interval
upper	<- tab[r, c("upper")]	#upper limit of 100*(1-2*alpha)% confidence interval
design	<- tab[r, c("Design")]	#design, type known.designs() to get coding
###-----------------------------------------------
### Jirka's CVfromCI code
if(is.na(point)){
CV <- CVfromCI(lower=lower,upper=upper,n=n,design=design,alpha=alpha)
} else {
CV <- CVfromCI(pe=point,lower=lower,upper=upper,n=n,design=design,alpha=alpha)
}
###-----------------------------------------------

CVcol <- append(CVcol, CV)

### Jirka's SampleSize code

theta1	<- tab[r, c("lowBElimit")]		#lower BE limit
theta2	<-1/theta1	#upper BE limit
# CV		<-c(.23)	#intrasubject coefficient of variation
design	<- tab[r, c("PlannedDesign")]	#design, (type 'known.designs()' after package is loaded)
###-----------------------------------------------
# res<-c()
####### TRY TO FEED DIRECTLY TO DF USING r for Row and n+a for every targetpower
a = 1
for(a in 1:length(targetpower)){
y <- sampleN.TOST(
alpha=alpha,
targetpower=targetpower[a],
logscale=TRUE,
theta1=theta1,
theta2=theta2,
theta0=theta0,
CV=CV,
design=design,
#method=method,
details=T,
print=T,
robust=FALSE,
imax=1000)
res[r, a]	<- y[,7]
#print(y)
#### WRITE TO DF FOR TARGETPOWER HERE
}
#print(y)

}

CVcolPct <- round(CVcol * 100, 0)
tab$CVw <- round(CVcolPct)
result <- cbind(tab, res)
print(result)

###-----------------------------------------
### Pooled CVw by PowerTOST - Script by Jirka
names(result)
cvpool <- result[result$Incl.to.PoolCVw == 'Y', ]
nrow(cvpool)

poolCmax <-cvpool[cvpool$PK=="Cmax", c('CVw', 'Ntotal', 'Design') ]
names(poolCmax) <- c('CV', 'n', 'design')

poolAUC <-cvpool[cvpool$PK=="AUC", c('CVw', 'Ntotal', 'Design') ]
names(poolAUC) <- c('CV', 'n', 'design')

poolCmaxRes <-CVpooled(poolCmax,
alpha=0.05,
logscale=T,
robust=F
)
print(poolCmaxRes, digits=5, verbose=T)

poolAUCRes <-CVpooled(poolAUC,
alpha=0.05,
logscale=T,
robust=F
)
print(poolAUCRes, digits=5, verbose=T)

###-----------------------------------------
### Write table of results
write.csv(result, file = "SS-result.csv")