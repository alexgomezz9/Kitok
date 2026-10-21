import React from 'react';
import {AbsoluteFill, Composition, Img, useCurrentFrame, useVideoConfig, interpolate, staticFile} from 'remotion';
// Original four-second benchmark, identical supplied photo/copy/audio to Native.
type Props = {name:string;label:string;detail:string};
const Portrait: React.FC<Props> = ({name,label,detail}) => {
 const f=useCurrentFrame();const {fps}=useVideoConfig();
 const alpha=interpolate(f,[0,.6*fps,3.2*fps,4*fps-1],[0,1,1,0],{extrapolateLeft:'clamp',extrapolateRight:'clamp'});
 return <AbsoluteFill style={{background:'black',fontFamily:'DejaVu Sans',color:'#F4EFE4'}}>
  <AbsoluteFill style={{opacity:alpha,overflow:'hidden'}}>
   <Img src={staticFile('photo.jpg')} style={{width:'100%',height:'100%',objectFit:'cover',filter:'blur(25px) brightness(.42)',scale:'1.1'}}/>
   <AbsoluteFill style={{alignItems:'center',justifyContent:'center',scale:interpolate(f,[0,119],[1,1.035])}}><Img src={staticFile('photo.jpg')} style={{height:'100%',objectFit:'contain'}}/></AbsoluteFill>
   <AbsoluteFill style={{background:'linear-gradient(transparent 35%,rgba(0,0,0,.78) 100%)'}}/>
   <div style={{position:'absolute',left:96,bottom:66}}>
    <div style={{fontSize:21,letterSpacing:5,color:'#E8B95D',marginBottom:10}}>{label}</div>
    <div style={{fontSize:65,fontWeight:700,clipPath:'inset(0)',translate:`0 ${interpolate(f,[0,12],[45,0],{extrapolateRight:'clamp'})}px`,opacity:interpolate(f,[0,7],[0,1],{extrapolateRight:'clamp'})}}>{name}</div>
    <div style={{fontSize:23,marginTop:12,color:'#B9BCC2'}}>{detail}</div>
   </div>
  </AbsoluteFill>
 </AbsoluteFill>;
};
export const MyComposition=()=> <Composition id="Portrait" component={Portrait} durationInFrames={120} fps={30} width={1280} height={720} defaultProps={{name:"Provided subject",label:"EDITORIAL DEMONSTRATION",detail:"Replace the supplied photograph and review its rights"}}/>;
