/*var myform = $("form#contactForm");
myform.submit(function(event){
    event.preventDefault();

  // Change to your service ID, or keep using the default service
  var service_id = "gmail";
  var template_id = "miscsoletrader";

  $('.btn').prop('disabled', true); // Button Disable
  myform.find("button").text("Wait..."); // Change Button Text
  emailjs.sendForm(service_id,template_id,myform[0])
    .then(function(){ 
       myform.find("button").text("Send"); // Display Sens text on Button
       $('.btn').prop('disabled', false); // Enable Button
       $('#success').show(); // Shhoe success alert
       myform.trigger("reset"); // rest all fileds on form
    }, function(err) {
       myform.find("button").text("Send");
    });
  return false;
});
*/
var myform = $("form#contactForm");
myform.submit(function(event){
	event.preventDefault();

  // Change to your service ID, or keep using the default service
  var service_id = "gmail";
  var template_id = "miscsoletrader";

  myform.find(".btn").text("Sending...");
  emailjs.sendForm(service_id,template_id,myform[0])
  	.then(function(){ 
    	alert("Sent!");
       myform.find(".btn").text("Send");
    }, function(err) {
       alert("Send email failed!\r\n Response:\n " + JSON.stringify(err));
       myform.find("btn").text("Send");
    });
  return false;
});