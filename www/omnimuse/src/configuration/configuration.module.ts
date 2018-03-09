import { BrowserModule } from '@angular/platform-browser';
import { NgModule } from '@angular/core';


import { ConfigurationComponent } from './configuration.component';


@NgModule({
  declarations: [
    ConfigurationComponent
  ],
  imports: [
    BrowserModule
  ],
  providers: [],
  bootstrap: [ConfigurationComponent]
})
export class ConfigurationModule { }
