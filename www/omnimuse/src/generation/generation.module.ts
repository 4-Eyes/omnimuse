import { BrowserModule } from '@angular/platform-browser';
import { NgModule } from '@angular/core';


import { GenerationComponent } from './generation.component';


@NgModule({
  declarations: [
    GenerationComponent
  ],
  imports: [
    BrowserModule
  ],
  providers: [],
  bootstrap: [GenerationComponent]
})
export class GenerationModule { }
