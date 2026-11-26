import React from "react";
import Svg, { Circle, Line, Path, Polyline, Rect } from "react-native-svg";

interface IconProps {
  size?: number;
  color?: string;
}

export const OverviewIcon: React.FC<IconProps> = ({ size = 20, color = "#9CA8BC" }) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
    <Rect x={3} y={3} width={7} height={9} rx={1.5} stroke={color} strokeWidth={1.8} />
    <Rect x={14} y={3} width={7} height={5} rx={1.5} stroke={color} strokeWidth={1.8} />
    <Rect x={14} y={12} width={7} height={9} rx={1.5} stroke={color} strokeWidth={1.8} />
    <Rect x={3} y={16} width={7} height={5} rx={1.5} stroke={color} strokeWidth={1.8} />
  </Svg>
);

export const ChartTabIcon: React.FC<IconProps> = ({ size = 20, color = "#9CA8BC" }) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
    <Line x1={6} y1={4} x2={6} y2={20} stroke={color} strokeWidth={1.6} strokeLinecap="round" />
    <Rect x={4} y={8} width={4} height={7} rx={1} fill={color} />
    <Line x1={12} y1={3} x2={12} y2={19} stroke={color} strokeWidth={1.6} strokeLinecap="round" />
    <Rect x={10} y={6} width={4} height={8} rx={1} stroke={color} strokeWidth={1.6} />
    <Line x1={18} y1={5} x2={18} y2={21} stroke={color} strokeWidth={1.6} strokeLinecap="round" />
    <Rect x={16} y={9} width={4} height={7} rx={1} fill={color} />
  </Svg>
);

export const TradesTabIcon: React.FC<IconProps> = ({ size = 20, color = "#9CA8BC" }) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
    <Polyline points="3,17 9,11 13,15 21,7" stroke={color} strokeWidth={1.9} strokeLinecap="round" strokeLinejoin="round" />
    <Polyline points="15,7 21,7 21,13" stroke={color} strokeWidth={1.9} strokeLinecap="round" strokeLinejoin="round" />
  </Svg>
);

export const SecurityTabIcon: React.FC<IconProps> = ({ size = 20, color = "#9CA8BC" }) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
    <Path
      d="M12 3L4 6.5V12c0 4.8 3.4 8.2 8 9.5 4.6-1.3 8-4.7 8-9.5V6.5L12 3z"
      stroke={color}
      strokeWidth={1.8}
      strokeLinejoin="round"
    />
    <Polyline points="9,12.5 11.2,14.7 15.5,10" stroke={color} strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" />
  </Svg>
);

export const SunIcon: React.FC<IconProps> = ({ size = 18, color = "#F59E0B" }) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
    <Circle cx={12} cy={12} r={4} stroke={color} strokeWidth={1.8} />
    <Line x1={12} y1={2} x2={12} y2={5} stroke={color} strokeWidth={1.8} strokeLinecap="round" />
    <Line x1={12} y1={19} x2={12} y2={22} stroke={color} strokeWidth={1.8} strokeLinecap="round" />
    <Line x1={2} y1={12} x2={5} y2={12} stroke={color} strokeWidth={1.8} strokeLinecap="round" />
    <Line x1={19} y1={12} x2={22} y2={12} stroke={color} strokeWidth={1.8} strokeLinecap="round" />
  </Svg>
);

export const MoonIcon: React.FC<IconProps> = ({ size = 18, color = "#6FF2C4" }) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
    <Path
      d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z"
      stroke={color}
      strokeWidth={1.8}
      strokeLinejoin="round"
    />
  </Svg>
);

export const FullscreenIcon: React.FC<IconProps> = ({ size = 16, color = "#9CA8BC" }) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
    <Polyline points="15,3 21,3 21,9" stroke={color} strokeWidth={1.9} strokeLinecap="round" strokeLinejoin="round" />
    <Polyline points="9,21 3,21 3,15" stroke={color} strokeWidth={1.9} strokeLinecap="round" strokeLinejoin="round" />
    <Line x1={21} y1={3} x2={14} y2={10} stroke={color} strokeWidth={1.9} strokeLinecap="round" />
    <Line x1={3} y1={21} x2={10} y2={14} stroke={color} strokeWidth={1.9} strokeLinecap="round" />
  </Svg>
);

export const ResetIcon: React.FC<IconProps> = ({ size = 16, color = "#9CA8BC" }) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
    <Path d="M3 12a9 9 0 1 0 3-6.7L3 8" stroke={color} strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" />
    <Polyline points="3,3 3,8 8,8" stroke={color} strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" />
  </Svg>
);

export const QrIcon: React.FC<IconProps> = ({ size = 18, color = "#062019" }) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
    <Rect x={3} y={3} width={7} height={7} rx={1} stroke={color} strokeWidth={1.8} />
    <Rect x={14} y={3} width={7} height={7} rx={1} stroke={color} strokeWidth={1.8} />
    <Rect x={3} y={14} width={7} height={7} rx={1} stroke={color} strokeWidth={1.8} />
    <Rect x={14} y={14} width={3} height={3} fill={color} />
    <Rect x={18} y={18} width={3} height={3} fill={color} />
  </Svg>
);
