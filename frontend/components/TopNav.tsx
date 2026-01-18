"use client"

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import React, {useEffect} from 'react'
import {BottomNavigation, BottomNavigationAction} from "@mui/material";
import PartnerIcon from '@mui/icons-material/AddBusiness';
import AccountIcon from '@mui/icons-material/AccountCircle';
import AddIcon from '@mui/icons-material/VideoCall';

export default function TopNav() {
  const pathname = usePathname() || '/'
  const [value, setValue] = React.useState(0);

    useEffect(() => {
        console.log(value)
    }, [value]);

  return (
      <div
        style={{
          position: 'fixed',
          bottom: 0,
          left: 0,
          right: 0,
          height: '150px',
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'flex-end',
          zIndex: 1000,
          overflow: 'hidden',
          pointerEvents: 'none',
        }}
      >
        {/* Organic blob SVG */}
        <svg
          viewBox="0 0 1000 150"
          preserveAspectRatio="none"
          style={{
            position: 'absolute',
            bottom: 0,
            left: '-5%',
            width: '110%',
            height: '160px',
          }}
        >
          {/* Main organic blob - solid fill, no gradients */}
          <path
            d="m -50,200 -1.253041,-66.10491 C -1.2530402,138.89509 80.000313,160 150.00031,140 270.7876,93.666554 377.11989,43.460348 500,42 c 125.51876,2.929291 237.08152,54.726713 350.00031,88 70,20 149.99999,35 199.99999,30 l -3e-4,40 z"
            fill="#4078F2"
          />
        </svg>

        {/* Navigation content */}
        <div
          style={{
            position: 'relative',
            zIndex: 10,
            paddingBottom: '20px',
            pointerEvents: 'auto',
          }}
        >
          <BottomNavigation
              showLabels
              value={value}
              onChange={(event, newValue) => {
                setValue(newValue);
              }}
              sx={{
                height: "60px",
                backgroundColor: 'transparent',
                '& .MuiBottomNavigationAction-root': {
                  color: 'rgba(255, 255, 255, 0.7)',
                  minWidth: '150px',
                  padding: '0 24px',
                  borderRadius: '16px',
                  transition: 'all 0.2s ease',
                  '&:hover': {
                      backgroundColor: 'rgba(255, 255, 255, 0.1)',
                    color: '#FAFAFA',
                    transform: 'translateY(-4px)',
                  },
                },
                '& .Mui-selected': {
                  color: '#FAFAFA',
                },
                '& .MuiBottomNavigationAction-label': {
                  color: '#FAFAFA',
                  fontWeight: 500,
                },
              }}
          >
            <BottomNavigationAction label={value == 0 && "Partners"} icon={<PartnerIcon color="info" style={{fontSize: "6vh"}}/>}/>
            <BottomNavigationAction label={value == 1 && "Create Clips"} icon={<AddIcon color="info" style={{fontSize: "6vh"}}/>} />
                <BottomNavigationAction label={value == 2 && "Account"} icon={<AccountIcon color="info" style={{fontSize: "6vh"}}/>} />
              </BottomNavigation>
            </div>
          </div>
      )
}
